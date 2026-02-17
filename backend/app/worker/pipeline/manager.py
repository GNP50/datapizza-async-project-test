"""
Generic Pipeline Manager for orchestrating document processing stages.

This module provides a flexible, configuration-driven pipeline manager that
can execute a sequence of stages with support for resumption, parallelization,
and error handling.
"""

import logging
from typing import Any, Optional
from uuid import UUID
import asyncio
from asyncio import Semaphore

from app.worker.pipeline.base import (
    BaseStage,
    StageContext,
    StageResult,
    StageConfig
)
from app.models.document import DocumentProcessingState
from app.worker.utils.errors import ProcessingError


logger = logging.getLogger(__name__)


class PipelineManager:
    """
    Generic pipeline manager for orchestrating document processing stages.

    The manager executes a sequence of stages in order, with support for:
    - Resuming from a specific stage based on document state
    - Parallel processing of multiple items
    - Error handling and recovery
    - State management and logging

    Example:
        # Create pipeline
        pipeline = PipelineManager([
            OCRStage(ocr_config),
            FactStage(fact_config),
            VerificationStage(verification_config),
        ])

        # Execute for a document
        result = await pipeline.execute_for_document(document_id, message_id)
    """

    def __init__(
        self,
        stages: list[BaseStage],
        name: str = "document_processing"
    ):
        """
        Initialize the pipeline manager.

        Args:
            stages: List of stages to execute in order
            name: Name of the pipeline (for logging)
        """
        self.stages = stages
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    def get_stage_order(self) -> list[str]:
        """Get the execution order of stages."""
        return [stage.config.name for stage in self.stages]

    def find_start_index(self, current_state: DocumentProcessingState) -> int:
        """
        Determine which stage to start from based on current document state.

        Args:
            current_state: Current processing state of the document

        Returns:
            Index of the stage to start from (0 = start from beginning)
        """
        # Map document states to stage names
        state_to_stage = {
            DocumentProcessingState.PENDING: None,  # Start from beginning
            DocumentProcessingState.OCR_EXTRACTION: "ocr_extraction",
            DocumentProcessingState.FACT_ATOMIZATION: "fact_atomization",
            DocumentProcessingState.WEB_VERIFICATION: "web_verification",
            DocumentProcessingState.QA_GENERATION: "qa_generation",
            DocumentProcessingState.VECTOR_INDEXING: "vector_indexing",
        }

        stage_name = state_to_stage.get(current_state)

        if stage_name is None:
            self.logger.info(f"Starting pipeline from beginning (state={current_state.value})")
            return 0

        # Find the stage index
        for idx, stage in enumerate(self.stages):
            if stage.config.name == stage_name:
                self.logger.info(f"Resuming pipeline from stage '{stage_name}' (index={idx})")
                return idx

        # If stage not found, start from beginning
        self.logger.warning(
            f"Could not find stage for state {current_state.value}, starting from beginning"
        )
        return 0

    async def execute_for_document(
        self,
        document_id: UUID,
        message_id: Optional[UUID] = None,
        chat_id: Optional[UUID] = None,
        current_state: Optional[DocumentProcessingState] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Execute the pipeline for a single document.

        Args:
            document_id: ID of the document to process
            message_id: ID of the associated message
            chat_id: ID of the associated chat
            current_state: Current processing state (for resumption)
            metadata: Additional metadata to pass to stages

        Returns:
            Dictionary with execution results and metadata

        Raises:
            ProcessingError: If pipeline execution fails
        """
        self.logger.info(
            f"Starting pipeline '{self.name}' for document {document_id}"
        )

        # Create stage context
        ctx = StageContext(
            document_id=document_id,
            message_id=message_id,
            chat_id=chat_id,
            metadata=metadata or {}
        )

        # Determine starting stage
        start_idx = 0
        if current_state:
            start_idx = self.find_start_index(current_state)

        # Execute stages sequentially
        stage_input = None
        last_successful_stage = None

        for idx, stage in enumerate(self.stages[start_idx:], start=start_idx):
            stage_name = stage.config.name

            try:
                # Execute stage
                result = await stage.run(ctx, stage_input)

                if not result.success:
                    error_msg = f"Stage '{stage_name}' failed: {result.error}"
                    self.logger.error(error_msg)

                    # Check if we should continue on error
                    if not stage.config.skip_on_error:
                        raise ProcessingError(error_msg) from result.error

                    # Skip to next stage
                    self.logger.warning(f"Continuing despite failure in stage '{stage_name}'")
                    continue

                # Store stage output for next stage
                stage_input = result.data
                last_successful_stage = stage_name

                # Store stage result in shared state
                ctx.set(f"stage_{stage_name}_result", result.data)
                ctx.set(f"stage_{stage_name}_metadata", result.metadata)

            except Exception as e:
                self.logger.error(
                    f"Unhandled error in stage '{stage_name}': {e}",
                    exc_info=True
                )
                raise ProcessingError(f"Pipeline failed at stage '{stage_name}': {str(e)}") from e

        self.logger.info(
            f"Pipeline '{self.name}' completed for document {document_id}"
        )

        return {
            "status": "completed",
            "document_id": str(document_id),
            "last_stage": last_successful_stage,
            "shared_state": ctx.shared_state
        }

    async def execute_batch(
        self,
        document_ids: list[UUID],
        message_id: Optional[UUID] = None,
        chat_id: Optional[UUID] = None,
        parallel: bool = False,
        max_concurrency: int = 3,
        max_retries: int = 3
    ) -> list[dict[str, Any]]:
        """
        Execute the pipeline for multiple documents.

        Args:
            document_ids: List of document IDs to process
            message_id: ID of the associated message
            chat_id: ID of the associated chat
            parallel: If True, process documents in parallel
            max_concurrency: Maximum number of concurrent executions
            max_retries: Maximum retry attempts per document

        Returns:
            List of results for each document
        """
        self.logger.info(
            f"Starting batch execution for {len(document_ids)} documents "
            f"(parallel={parallel}, max_concurrency={max_concurrency})"
        )

        if not parallel or len(document_ids) <= 1:
            # Sequential processing
            results = []
            for doc_id in document_ids:
                result = await self.execute_for_document(
                    document_id=doc_id,
                    message_id=message_id,
                    chat_id=chat_id
                )
                results.append(result)
            return results

        # Parallel processing with concurrency limit
        semaphore = Semaphore(max_concurrency)

        async def process_with_retry(doc_id: UUID) -> dict[str, Any]:
            """Process a single document with retry logic."""
            async with semaphore:
                last_error = None
                for attempt in range(max_retries):
                    try:
                        return await self.execute_for_document(
                            document_id=doc_id,
                            message_id=message_id,
                            chat_id=chat_id
                        )
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            self.logger.warning(
                                f"Document {doc_id} retry {attempt + 1}/{max_retries}: {e}"
                            )
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            self.logger.error(
                                f"Document {doc_id} failed after {max_retries} retries"
                            )

                # Return error result
                return {
                    "status": "failed",
                    "document_id": str(doc_id),
                    "error": str(last_error)
                }

        # Execute all documents in parallel
        tasks = [process_with_retry(doc_id) for doc_id in document_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        processed_results = []
        for doc_id, result in zip(document_ids, results):
            if isinstance(result, Exception):
                processed_results.append({
                    "status": "failed",
                    "document_id": str(doc_id),
                    "error": str(result)
                })
            else:
                processed_results.append(result)

        return processed_results

    def add_stage(self, stage: BaseStage, position: Optional[int] = None) -> None:
        """
        Add a stage to the pipeline.

        Args:
            stage: Stage to add
            position: Position to insert at (None = append to end)
        """
        if position is None:
            self.stages.append(stage)
        else:
            self.stages.insert(position, stage)

        self.logger.info(f"Added stage '{stage.config.name}' to pipeline '{self.name}'")

    def remove_stage(self, stage_name: str) -> bool:
        """
        Remove a stage from the pipeline by name.

        Args:
            stage_name: Name of the stage to remove

        Returns:
            True if stage was removed, False if not found
        """
        for idx, stage in enumerate(self.stages):
            if stage.config.name == stage_name:
                self.stages.pop(idx)
                self.logger.info(f"Removed stage '{stage_name}' from pipeline '{self.name}'")
                return True

        self.logger.warning(f"Stage '{stage_name}' not found in pipeline '{self.name}'")
        return False

    def get_stage(self, stage_name: str) -> Optional[BaseStage]:
        """
        Get a stage by name.

        Args:
            stage_name: Name of the stage to retrieve

        Returns:
            Stage instance or None if not found
        """
        for stage in self.stages:
            if stage.config.name == stage_name:
                return stage
        return None

    def __repr__(self) -> str:
        stage_names = ", ".join(s.config.name for s in self.stages)
        return f"PipelineManager(name='{self.name}', stages=[{stage_names}])"
