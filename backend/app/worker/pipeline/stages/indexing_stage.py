"""
Stage E: Vector Store Indexing

Index Q&A pairs, document chunks, and AI summary into vector store.
Implements the BaseStage pattern for modular pipeline execution.
"""

import logging
from uuid import UUID, uuid4
from typing import Optional

from sqlalchemy import select

from datapizza.type import Chunk, DenseEmbedding
from app.worker.pipeline.base import BaseStage, StageContext, StageConfig
from app.services.database import db_manager
from app.models.document import Document, DocumentProcessingState
from app.models.message import Message, ProcessingState
from app.services.rag import semantic_cache, document_processor
from app.services.rag.vectorstore import vectorstore
from app.services.rag.embedder import embedder
from app.services.llm import llm_client
from app.services.storage import storage_manager
from app.worker.utils.errors import ProcessingError


logger = logging.getLogger(__name__)


SUMMARY_SYSTEM_PROMPT = """You are a professional document summarizer. Create a comprehensive summary of the document.

RULES:
- Write a detailed summary that covers ALL key points, main themes, and important information.
- Structure the summary with clear sections if the document covers multiple topics.
- Include specific data points, names, dates, and numbers when present.
- The summary should be self-contained — a reader should understand the document's content from the summary alone.
- Write in the same language as the document.
- Be thorough but avoid unnecessary repetition."""


class VectorIndexingStage(BaseStage[list[dict], int]):
    """
    Stage E: Vector Store Indexing

    Indexes three types of content into the vector store:
    1. Q&A pairs (for semantic cache - fast verified-fact retrieval)
    2. Raw document chunks (for RAG fallback when cache misses)
    3. AI-generated document summary (for high-level overview)

    Configuration:
        - custom_params.index_qa_pairs: Index Q&A pairs (default: True)
        - custom_params.index_chunks: Index document chunks (default: True)
        - custom_params.generate_summary: Generate and index summary (default: True)
        - custom_params.max_summary_chars: Max chars for summary generation (default: 12000)
    """

    def __init__(self, config: StageConfig):
        super().__init__(config)

    async def execute(self, ctx: StageContext, input_data: list[dict]) -> int:
        """
        Index Q&A pairs, chunks, and summary into vector store.

        Args:
            ctx: Stage context with document_id and chat_id
            input_data: Q&A pairs from previous stage

        Returns:
            Total number of items indexed
        """
        document_id = ctx.document_id
        qa_pairs = input_data or ctx.get("qa_pairs", [])

        # Get document and message info
        async with db_manager.session() as db:
            result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            if not document:
                raise ProcessingError(f"Document {document_id} not found")

            result = await db.execute(
                select(Message).where(Message.id == document.message_id)
            )
            message = result.scalar_one_or_none()
            if not message:
                raise ProcessingError(f"Message {document.message_id} not found")

            chat_id = message.chat_id
            file_path = document.file_path
            filename = document.filename

        # Store chat_id in context if not already set
        if not ctx.chat_id:
            ctx.chat_id = chat_id

        total_indexed = 0

        # 1. Index Q&A pairs into semantic cache
        if self.config.custom_params.get("index_qa_pairs", True) and qa_pairs:
            indexed_count = await self._index_qa_pairs(qa_pairs, document_id, chat_id, filename)
            total_indexed += indexed_count

        # 2. Index raw document chunks for RAG fallback
        full_text = ""
        if self.config.custom_params.get("index_chunks", True):
            full_text = await self._get_full_text(file_path, filename, document_id)
            if full_text.strip():
                chunk_count = await self._index_document_chunks(
                    document_id, chat_id, full_text, filename
                )
                total_indexed += chunk_count

        # 3. Generate and index AI summary
        if self.config.custom_params.get("generate_summary", True):
            if not full_text:
                full_text = await self._get_full_text(file_path, filename, document_id)

            if full_text.strip():
                summary_indexed = await self._generate_and_index_summary(
                    document_id, chat_id, filename, full_text
                )
                if summary_indexed:
                    total_indexed += 1

        # Mark document as completed
        from app.worker.utils.state import update_document_state
        await update_document_state(document_id, DocumentProcessingState.COMPLETED)

        # Store result in context
        ctx.set("total_indexed", total_indexed)

        self.logger.info(
            f"Vector indexing completed: {total_indexed} total items indexed for chat {chat_id}"
        )
        return total_indexed

    async def _index_qa_pairs(
        self,
        qa_pairs: list[dict],
        document_id: UUID,
        chat_id: UUID,
        filename: str
    ) -> int:
        """Index Q&A pairs into semantic cache."""
        # Enrich QA pairs metadata with filename for attribution
        for qa in qa_pairs:
            if "metadata" not in qa:
                qa["metadata"] = {}
            qa["metadata"]["filename"] = filename

        indexed_count = await semantic_cache.index_qa_pairs(
            qa_pairs=qa_pairs,
            document_id=document_id,
            chat_id=chat_id
        )

        self.logger.info(f"Indexed {indexed_count} Q&A pairs for document {document_id}")
        return indexed_count

    async def _index_document_chunks(
        self,
        document_id: UUID,
        chat_id: UUID,
        full_text: str,
        filename: str
    ) -> int:
        """Index raw document chunks for RAG fallback."""
        try:
            chunk_ids = await document_processor.process_document(
                document_id=document_id,
                chat_id=chat_id,
                text=full_text,
                metadata={"filename": filename, "type": "document_chunk"}
            )
            self.logger.info(f"Indexed {len(chunk_ids)} document chunks for RAG fallback")
            return len(chunk_ids)

        except Exception as e:
            # Don't fail the whole stage if chunk indexing fails
            self.logger.warning(f"Failed to index document chunks (non-fatal): {e}")
            return 0

    async def _generate_and_index_summary(
        self,
        document_id: UUID,
        chat_id: UUID,
        filename: str,
        full_text: str
    ) -> bool:
        """Generate an AI summary and index it in vector store."""
        try:
            # Truncate text if too long for LLM context
            max_chars = self.config.custom_params.get("max_summary_chars", 12000)
            text_for_summary = full_text[:max_chars]
            if len(full_text) > max_chars:
                text_for_summary += "\n\n[... document truncated for summary generation ...]"

            prompt = (
                f"Document: '{filename}'\n\n"
                f"Content:\n{text_for_summary}\n\n"
                f"Provide a comprehensive summary of this document."
            )

            response = await llm_client.a_invoke(
                input=prompt,
                system_prompt=SUMMARY_SYSTEM_PROMPT
            )
            summary = response.text.strip()

            if not summary:
                self.logger.warning(f"LLM returned empty summary for document {document_id}")
                return False

            self.logger.info(f"Generated summary for document {document_id} ({len(summary)} chars)")

            # Index summary in vector store
            summary_embedding = await embedder.a_embed([summary])
            summary_chunk = Chunk(
                id=str(uuid4()),
                text=summary,
                metadata={
                    "type": "document_summary",
                    "document_id": str(document_id),
                    "filename": filename,
                },
                embeddings=[DenseEmbedding(name="default", vector=summary_embedding[0])]
            )
            await vectorstore.a_add(summary_chunk, chat_id=chat_id)
            self.logger.info(f"Indexed document summary in vector store for document {document_id}")

            # Save summary to database
            async with db_manager.session() as db:
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                doc = result.scalar_one_or_none()
                if doc:
                    doc.summary = summary
                    await db.commit()
                    self.logger.info(f"Saved summary to database for document {document_id}")

            return True

        except Exception as e:
            self.logger.warning(f"Failed to generate/index document summary (non-fatal): {e}")
            return False

    async def _get_full_text(
        self,
        file_path: str,
        filename: str,
        document_id: UUID
    ) -> str:
        """Get full text from storage or context."""
        try:
            md_path = file_path.replace(filename, f"{document_id}.md")
            full_text_bytes = await storage_manager.download(md_path)
            return full_text_bytes.decode("utf-8")
        except Exception as e:
            self.logger.warning(f"Failed to download full text from storage: {e}")
            return ""

    @classmethod
    def from_settings(cls, settings) -> 'VectorIndexingStage':
        """Create VectorIndexingStage from application settings."""
        config = StageConfig.from_settings(
            settings,
            stage_name="vector_indexing",
            document_state=DocumentProcessingState.VECTOR_INDEXING,
            message_state=ProcessingState.VECTOR_INDEXING,
            cache_enabled=False,  # No caching for indexing stage
            custom_params={
                "index_qa_pairs": True,
                "index_chunks": True,
                "generate_summary": True,
                "max_summary_chars": 12000
            }
        )
        return cls(config)
