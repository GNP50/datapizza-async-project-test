"""
Base classes for pipeline stages with ABC pattern.

This module provides abstract base classes and utilities for implementing
modular, configurable pipeline stages for document processing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, TypeVar, Generic
from uuid import UUID
import logging

from app.models.document import DocumentProcessingState
from app.models.message import ProcessingState


logger = logging.getLogger(__name__)


# Type variable for stage input/output
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')


@dataclass
class StageConfig:
    """
    Configuration for a pipeline stage.

    This class encapsulates all configurable parameters for a stage,
    allowing stages to be self-contained and configuration-driven.
    """
    # Stage identification
    name: str
    enabled: bool = True

    # Execution control
    skip_on_error: bool = False
    max_retries: int = 3
    retry_backoff: float = 2.0  # Exponential backoff multiplier

    # Parallelization
    parallel_enabled: bool = False
    max_concurrency: int = 3

    # Caching
    cache_enabled: bool = True
    cache_stage_name: Optional[str] = None  # Override cache key

    # State management
    document_state: Optional[DocumentProcessingState] = None
    message_state: Optional[ProcessingState] = None

    # Custom parameters (stage-specific)
    custom_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: Any, stage_name: str, **overrides) -> 'StageConfig':
        """
        Create a StageConfig from application settings.

        Args:
            settings: Application settings object
            stage_name: Name of the stage (e.g., 'ocr_extraction', 'fact_atomization')
            **overrides: Additional parameters to override defaults

        Returns:
            StageConfig instance
        """
        # Extract parallelization settings
        parallel_key = f"{stage_name}_parallel"
        concurrency_key = f"{stage_name}_max_concurrency"
        retries_key = f"{stage_name}_max_retries"

        config = cls(
            name=stage_name,
            parallel_enabled=getattr(settings, parallel_key, False),
            max_concurrency=getattr(settings, concurrency_key, 3),
            max_retries=getattr(settings, retries_key, 3),
            **overrides
        )

        logger.debug(
            f"Created StageConfig for '{stage_name}': "
            f"parallel={config.parallel_enabled}, "
            f"concurrency={config.max_concurrency}, "
            f"retries={config.max_retries}"
        )

        return config


@dataclass
class StageContext:
    """
    Context object passed to each stage during execution.

    Contains all necessary information for stage execution including
    document metadata, database session, and shared state.
    """
    document_id: UUID
    message_id: Optional[UUID] = None
    chat_id: Optional[UUID] = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Shared state between stages
    shared_state: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from shared state."""
        return self.shared_state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set value in shared state."""
        self.shared_state[key] = value


@dataclass
class StageResult(Generic[TOutput]):
    """
    Result of a stage execution.

    Encapsulates the output data, success status, and any metadata
    produced by the stage.
    """
    success: bool
    data: Optional[TOutput] = None
    error: Optional[Exception] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: TOutput, **metadata) -> 'StageResult[TOutput]':
        """Create a successful result."""
        return cls(success=True, data=data, metadata=metadata)

    @classmethod
    def fail(cls, error: Exception, **metadata) -> 'StageResult[TOutput]':
        """Create a failed result."""
        return cls(success=False, error=error, metadata=metadata)


class BaseStage(ABC, Generic[TInput, TOutput]):
    """
    Abstract base class for all pipeline stages.

    Each stage must implement the `execute` method which contains the core
    processing logic. The stage is configured via a StageConfig object and
    can access shared context during execution.

    Example:
        class OCRStage(BaseStage[None, dict]):
            async def execute(self, ctx: StageContext, input_data: None) -> dict:
                # OCR processing logic
                return {"text": "extracted text"}
    """

    def __init__(self, config: StageConfig):
        """
        Initialize the stage with configuration.

        Args:
            config: StageConfig object containing all stage parameters
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def execute(
        self,
        ctx: StageContext,
        input_data: TInput
    ) -> TOutput:
        """
        Execute the stage logic.

        Args:
            ctx: Stage context with document metadata and shared state
            input_data: Input data from previous stage (or None for first stage)

        Returns:
            Output data to be passed to next stage

        Raises:
            ProcessingError: If stage execution fails
        """
        pass

    async def pre_execute(self, ctx: StageContext) -> None:
        """
        Hook called before execute(). Override to add setup logic.

        Args:
            ctx: Stage context
        """
        pass

    async def post_execute(self, ctx: StageContext, result: TOutput) -> None:
        """
        Hook called after successful execute(). Override to add cleanup logic.

        Args:
            ctx: Stage context
            result: Result from execute()
        """
        pass

    async def on_error(self, ctx: StageContext, error: Exception) -> None:
        """
        Hook called when execute() raises an exception. Override to add error handling.

        Args:
            ctx: Stage context
            error: Exception that was raised
        """
        pass

    def should_skip(self, ctx: StageContext) -> bool:
        """
        Determine if this stage should be skipped.

        Args:
            ctx: Stage context

        Returns:
            True if stage should be skipped, False otherwise
        """
        return not self.config.enabled

    async def run(
        self,
        ctx: StageContext,
        input_data: TInput
    ) -> StageResult[TOutput]:
        """
        Run the stage with full lifecycle (pre/execute/post/error hooks).

        This method orchestrates the complete stage execution including:
        - Skip checks
        - State updates
        - Pre/post hooks
        - Error handling
        - Retry logic

        Args:
            ctx: Stage context
            input_data: Input data from previous stage

        Returns:
            StageResult with success status and output data
        """
        stage_name = self.config.name

        # Check if stage should be skipped
        if self.should_skip(ctx):
            self.logger.info(f"Stage '{stage_name}' skipped (disabled)")
            return StageResult.ok(None, skipped=True)

        self.logger.info(f"Running stage '{stage_name}' for document {ctx.document_id}")

        # Update processing states
        if self.config.message_state and ctx.message_id:
            from app.worker.utils.state import update_message_state
            await update_message_state(str(ctx.message_id), self.config.message_state)

        if self.config.document_state:
            from app.worker.utils.state import update_document_state
            await update_document_state(ctx.document_id, self.config.document_state)

        # Execute with retry logic
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                # Pre-execute hook
                await self.pre_execute(ctx)

                # Main execution
                result = await self.execute(ctx, input_data)

                # Post-execute hook
                await self.post_execute(ctx, result)

                self.logger.info(f"Stage '{stage_name}' completed successfully")
                return StageResult.ok(result, attempts=attempt + 1)

            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"Stage '{stage_name}' failed (attempt {attempt + 1}/{self.config.max_retries}): {e}"
                )

                # Call error hook
                await self.on_error(ctx, e)

                # If skip_on_error, return partial success
                if self.config.skip_on_error:
                    self.logger.warning(f"Stage '{stage_name}' failed but skip_on_error=True")
                    return StageResult.fail(e, skipped=True, attempts=attempt + 1)

                # Retry with backoff
                if attempt < self.config.max_retries - 1:
                    import asyncio
                    backoff_time = self.config.retry_backoff ** attempt
                    self.logger.info(f"Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)

        # All retries exhausted
        self.logger.error(f"Stage '{stage_name}' failed after {self.config.max_retries} attempts")
        return StageResult.fail(last_error, attempts=self.config.max_retries)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.config.name}')"
