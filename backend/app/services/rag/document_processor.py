import logging
from uuid import UUID, uuid4
from datapizza.type import Chunk, DenseEmbedding
from .vectorstore import vectorstore
from .embedder import embedder

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 200):
        """
        Initialize document processor with semantic-aware chunking.

        Args:
            chunk_size: Target size for chunks (chars). Increased from 500 to 800 for better context.
            chunk_overlap: Overlap between chunks. Increased from 50 to 200 to preserve context continuity.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> list[tuple[str, dict]]:
        """
        Split text into semantic chunks with metadata.

        Tries to split at natural boundaries (paragraphs, sentences) rather than arbitrary positions.
        Returns list of (chunk_text, metadata) tuples where metadata contains structural info.
        """
        # First, split by double newlines (paragraphs)
        paragraphs = text.split('\n\n')

        chunks_with_meta = []
        current_chunk = ""
        chunk_index = 0

        # Track markdown headers for context
        current_headers = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Detect markdown headers
            if para.startswith('#'):
                # Extract header level and text
                header_level = len(para) - len(para.lstrip('#'))
                header_text = para.lstrip('#').strip()

                # Update current header hierarchy
                if header_level <= len(current_headers):
                    current_headers = current_headers[:header_level-1]
                if header_level > 0:
                    if len(current_headers) < header_level:
                        current_headers.extend([''] * (header_level - len(current_headers)))
                    if header_level <= len(current_headers):
                        current_headers[header_level-1] = header_text
                    else:
                        current_headers.append(header_text)

            # Check if adding this paragraph would exceed chunk size
            if len(current_chunk) + len(para) + 2 > self.chunk_size and current_chunk:
                # Save current chunk with metadata
                metadata = {
                    "chunk_index": chunk_index,
                    "headers": current_headers.copy() if current_headers else [],
                    "context": " > ".join(h for h in current_headers if h) if current_headers else ""
                }
                chunks_with_meta.append((current_chunk.strip(), metadata))
                chunk_index += 1

                # Start new chunk with overlap
                # Try to include last sentence(s) for continuity
                overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                current_chunk = overlap_text + "\n\n" + para if overlap_text else para
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

        # Add final chunk
        if current_chunk:
            metadata = {
                "chunk_index": chunk_index,
                "headers": current_headers.copy() if current_headers else [],
                "context": " > ".join(h for h in current_headers if h) if current_headers else ""
            }
            chunks_with_meta.append((current_chunk.strip(), metadata))

        logger.info(f"Created {len(chunks_with_meta)} semantic chunks from {len(text)} chars")
        return chunks_with_meta

    def _get_overlap_text(self, text: str, max_overlap_size: int) -> str:
        """Get the last portion of text for overlap, trying to break at sentence boundaries."""
        if len(text) <= max_overlap_size:
            return text

        # Try to find last sentence boundary within overlap size
        overlap_candidate = text[-max_overlap_size:]

        # Look for sentence endings
        for delimiter in ['. ', '.\n', '! ', '?\n', '? ']:
            last_idx = overlap_candidate.rfind(delimiter)
            if last_idx > max_overlap_size // 2:  # At least half the overlap size
                return overlap_candidate[last_idx + len(delimiter):].strip()

        # Fallback: just return last max_overlap_size chars
        return overlap_candidate

    async def process_document(
        self,
        document_id: UUID,
        chat_id: UUID,
        text: str,
        metadata: dict | None = None
    ) -> list[str]:
        """
        Process document into semantic chunks with rich metadata and index into vectorstore.

        Args:
            document_id: Document ID
            chat_id: Chat ID for isolation
            text: Full document text
            metadata: Base metadata (filename, type, etc.)

        Returns:
            List of chunk IDs that were indexed
        """
        chunks_with_meta = self.chunk_text(text)
        logger.info(f"Processing document {document_id}: {len(chunks_with_meta)} semantic chunks from {len(text)} chars")

        datapizza_chunks = []
        base_metadata = metadata or {}

        for chunk_text, chunk_metadata in chunks_with_meta:
            # Enrich chunk text with context if headers are available
            context_prefix = ""
            if chunk_metadata.get("context"):
                context_prefix = f"[Context: {chunk_metadata['context']}]\n\n"

            # Create enriched chunk text for better embedding
            enriched_text = context_prefix + chunk_text

            chunk = Chunk(
                id=str(uuid4()),
                text=enriched_text,  # Use enriched text for embedding
                metadata={
                    "document_id": str(document_id),
                    "chunk_index": chunk_metadata["chunk_index"],
                    "headers": chunk_metadata.get("headers", []),
                    "context": chunk_metadata.get("context", ""),
                    "original_text": chunk_text,  # Store original for retrieval
                    **base_metadata
                }
            )
            datapizza_chunks.append(chunk)

        # Generate embeddings for all enriched chunks
        texts = [chunk.text for chunk in datapizza_chunks]
        embeddings_result = await embedder.a_embed(texts)

        # Attach embeddings to chunks
        for chunk, embedding_vector in zip(datapizza_chunks, embeddings_result):
            chunk.embeddings = [DenseEmbedding(name="default", vector=embedding_vector)]

        await vectorstore.a_add(datapizza_chunks, chat_id=chat_id)
        logger.info(f"Indexed {len(datapizza_chunks)} enriched chunks for document {document_id} in chat {chat_id}")

        return [chunk.id for chunk in datapizza_chunks]

    async def search_relevant_context(
        self,
        query: str,
        chat_id: UUID,
        document_id: UUID | None = None,
        limit: int = 5,
        min_score: float = 0.3
    ) -> tuple[str, list[str]]:
        """
        Search for relevant document context.

        Returns:
            tuple of (formatted_context_string, list_of_matched_document_ids)
        """
        filter_dict = {}
        if document_id:
            filter_dict["document_id"] = str(document_id)

        logger.debug(f"Searching context: query='{query[:80]}...', chat_id={chat_id}, doc_id={document_id}, limit={limit}, min_score={min_score}")

        try:
            results = await vectorstore.a_search(
                query,
                chat_id=chat_id,
                top_k=limit,
                filter=filter_dict if filter_dict else None
            )
        except Exception as e:
            logger.error(f"Vectorstore search failed: {e}", exc_info=True)
            return "", []

        context_parts = []
        matched_doc_ids = []
        for i, chunk in enumerate(results, 1):
            score = getattr(chunk, 'score', 0.0)
            metadata = chunk.metadata or {}
            logger.debug(f"  Result {i}: score={score:.3f}, text='{chunk.text[:60]}...'")
            if score >= min_score:
                # Include filename in context so the LLM knows which document it comes from
                filename = metadata.get("filename", "")
                doc_id = metadata.get("document_id", "")
                chunk_type = metadata.get("type", "document_chunk")
                context_info = metadata.get("context", "")

                # Use original_text if available (without context prefix)
                display_text = metadata.get("original_text", chunk.text)

                if chunk_type == "qa_pair":
                    # For QA pairs, show the answer directly
                    answer = metadata.get("answer", display_text)
                    label = f"[From '{filename}']" if filename else f"[Context {i}]"
                    context_parts.append(f"{label} {answer}")
                elif chunk_type == "document_summary":
                    label = f"[Summary of '{filename}']" if filename else f"[Summary]"
                    context_parts.append(f"{label} {display_text}")
                else:
                    # For document chunks, include context hierarchy if available
                    if context_info and filename:
                        label = f"[From '{filename}' - {context_info}]"
                    elif filename:
                        label = f"[From '{filename}']"
                    else:
                        label = f"[Context {i}]"
                    context_parts.append(f"{label} {display_text}")

                if doc_id and doc_id not in matched_doc_ids:
                    matched_doc_ids.append(doc_id)

        if not context_parts:
            logger.info(f"No results above min_score={min_score} for query '{query[:80]}...' (got {len(results)} results, best score: {max((getattr(r, 'score', 0.0) for r in results), default=0.0):.3f})")

        return "\n\n".join(context_parts), matched_doc_ids


document_processor = DocumentProcessor()
