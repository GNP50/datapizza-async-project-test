# Pipeline Architecture Documentation

## Overview

The document processing pipeline is built using a modular, configuration-driven architecture based on the **Abstract Base Class (ABC) pattern**. This design allows for:

- **Modularity**: Each stage is self-contained and independent
- **Configurability**: All stages are configured via `StageConfig` objects
- **Extensibility**: Easy to add, remove, or reorder stages
- **Resumption**: Pipeline can resume from any stage based on document state
- **Parallelization**: Configurable parallel processing at multiple levels
- **Caching**: Content-hash based caching to avoid redundant processing

## Architecture Components

### 1. Base Classes (`base.py`)

#### `StageConfig`
Configuration object for a pipeline stage. Contains:
- **Identification**: `name`, `enabled`
- **Execution control**: `skip_on_error`, `max_retries`, `retry_backoff`
- **Parallelization**: `parallel_enabled`, `max_concurrency`
- **Caching**: `cache_enabled`, `cache_stage_name`
- **State management**: `document_state`, `message_state`
- **Custom parameters**: `custom_params` (dict for stage-specific settings)

#### `StageContext`
Context object passed to each stage during execution. Contains:
- Document/message/chat IDs
- Metadata
- Shared state (for passing data between stages)

#### `StageResult`
Result of a stage execution. Contains:
- Success status
- Output data
- Error (if failed)
- Metadata

#### `BaseStage`
Abstract base class for all pipeline stages. Key methods:
- `execute(ctx, input_data)`: **[ABSTRACT]** Core processing logic
- `pre_execute(ctx)`: Hook called before execute
- `post_execute(ctx, result)`: Hook called after successful execute
- `on_error(ctx, error)`: Hook called on error
- `should_skip(ctx)`: Determine if stage should be skipped
- `run(ctx, input_data)`: Full lifecycle execution (handles retries, state updates, etc.)

### 2. Pipeline Manager (`manager.py`)

#### `PipelineManager`
Orchestrates execution of multiple stages. Key features:
- Sequential stage execution
- Resumption from specific stage based on document state
- Batch processing with parallelization
- Error handling and recovery
- Dynamic stage addition/removal

Key methods:
- `execute_for_document(document_id, ...)`: Execute pipeline for single document
- `execute_batch(document_ids, ...)`: Execute pipeline for multiple documents
- `add_stage(stage, position)`: Add a stage to the pipeline
- `remove_stage(stage_name)`: Remove a stage by name
- `get_stage(stage_name)`: Get a stage by name

### 3. Pipeline Stages (`stages/`)

All stages inherit from `BaseStage` and implement the `execute()` method.

#### Stage A: OCR & Text Extraction (`ocr_stage.py`)
- **Input**: None (first stage)
- **Output**: `dict` with extracted text, pages, metadata
- **Caching**: By content hash
- **Features**:
  - Direct text extraction for textual files (.txt, .md, code files)
  - OCR service for PDF and image files
  - Encoding detection for text files

#### Stage B: Fact Atomization (`fact_stage.py`)
- **Input**: `dict` (OCR output)
- **Output**: `list[Fact]`
- **Caching**: By extracted text hash
- **Features**:
  - LLM-based fact extraction
  - Configurable max facts per document

#### Stage C: Web Verification (`verification_stage.py`)
- **Input**: `list[Fact]`
- **Output**: `int` (verified count)
- **Caching**: By fact content hash (per fact)
- **Parallelization**: Supports parallel fact verification
- **Features**:
  - Web search via DuckDuckGo
  - LLM judge for result analysis
  - Content extraction and indexing of verified sources
  - Inappropriate content filtering

#### Stage D: Q&A Generation (`qa_stage.py`)
- **Input**: `int` (verified count)
- **Output**: `list[dict]` (Q&A pairs)
- **Caching**: By facts content hash
- **Features**:
  - Generates multiple Q&A pairs per fact
  - Configurable pairs per fact
  - Includes uncertain facts (configurable)

#### Stage E: Vector Indexing (`indexing_stage.py`)
- **Input**: `list[dict]` (Q&A pairs)
- **Output**: `int` (total indexed)
- **Caching**: Disabled
- **Features**:
  - Indexes Q&A pairs into semantic cache
  - Indexes raw document chunks for RAG fallback
  - Generates and indexes AI summary

## Configuration

### From Settings (`.env` or `config.yaml`)

Each stage can be configured from application settings:

```python
# Parallelization
ocr_parallel=true
ocr_max_concurrency=3
ocr_max_retries=3

documents_parallel=true
documents_max_concurrency=2
documents_max_retries=3

web_verification_parallel=true
web_verification_max_concurrency=5
web_verification_max_retries=2
```

### Creating Stages

Each stage provides a `from_settings()` class method:

```python
from app.core.config import get_settings
from app.worker.pipeline.stages import OCRStage

settings = get_settings()
ocr_stage = OCRStage.from_settings(settings)
```

Or create with custom config:

```python
from app.worker.pipeline.base import StageConfig
from app.worker.pipeline.stages import OCRStage

config = StageConfig(
    name="ocr_extraction",
    enabled=True,
    parallel_enabled=False,
    max_concurrency=3,
    max_retries=3,
    cache_enabled=True,
    custom_params={
        "ocr_confidence_threshold": 0.7
    }
)
ocr_stage = OCRStage(config)
```

## Usage Examples

### Creating a Pipeline

```python
from app.core.config import get_settings
from app.worker.pipeline.manager import PipelineManager
from app.worker.pipeline.stages import (
    OCRStage,
    FactAtomizationStage,
    WebVerificationStage,
    QAGenerationStage,
    VectorIndexingStage,
)

settings = get_settings()

# Create pipeline with all stages
pipeline = PipelineManager(
    stages=[
        OCRStage.from_settings(settings),
        FactAtomizationStage.from_settings(settings),
        WebVerificationStage.from_settings(settings),
        QAGenerationStage.from_settings(settings),
        VectorIndexingStage.from_settings(settings),
    ],
    name="document_processing"
)
```

### Processing a Single Document

```python
from uuid import UUID

result = await pipeline.execute_for_document(
    document_id=UUID("..."),
    message_id=UUID("..."),
    chat_id=UUID("...")
)
```

### Processing Multiple Documents (Parallel)

```python
results = await pipeline.execute_batch(
    document_ids=[UUID("..."), UUID("..."), ...],
    message_id=UUID("..."),
    chat_id=UUID("..."),
    parallel=True,
    max_concurrency=3,
    max_retries=3
)
```

### Resuming from a Specific Stage

```python
from app.models.document import DocumentProcessingState

# Pipeline will automatically resume from FACT_ATOMIZATION
result = await pipeline.execute_for_document(
    document_id=UUID("..."),
    current_state=DocumentProcessingState.FACT_ATOMIZATION
)
```

### Adding a Custom Stage

```python
# Add a new stage at a specific position
custom_stage = MyCustomStage.from_settings(settings)
pipeline.add_stage(custom_stage, position=2)  # Insert after Stage A

# Or append to end
pipeline.add_stage(custom_stage)
```

### Removing a Stage

```python
pipeline.remove_stage("web_verification")
```

## Creating Custom Stages

### Step 1: Define Stage Class

```python
from app.worker.pipeline.base import BaseStage, StageContext, StageConfig
from typing import Optional

class MyCustomStage(BaseStage[InputType, OutputType]):
    """
    Custom stage description.

    Configuration:
        - custom_params.my_param: Description (default: value)
    """

    def __init__(self, config: StageConfig):
        super().__init__(config)
        # Additional initialization if needed

    async def execute(self, ctx: StageContext, input_data: InputType) -> OutputType:
        """
        Stage logic.

        Args:
            ctx: Stage context
            input_data: Output from previous stage

        Returns:
            Output for next stage
        """
        # Your processing logic here

        # Access custom params
        my_param = self.config.custom_params.get("my_param", "default")

        # Store data in context for later stages
        ctx.set("my_data", some_value)

        # Return output
        return result

    @classmethod
    def from_settings(cls, settings) -> 'MyCustomStage':
        """Create stage from application settings."""
        config = StageConfig.from_settings(
            settings,
            stage_name="my_custom_stage",
            document_state=DocumentProcessingState.MY_STATE,  # Add to enum
            message_state=ProcessingState.MY_STATE,           # Add to enum
            cache_enabled=True,
            custom_params={
                "my_param": "default_value"
            }
        )
        return cls(config)
```

### Step 2: Add to Pipeline

```python
from app.worker.pipeline.stages import MyCustomStage

pipeline = PipelineManager(
    stages=[
        OCRStage.from_settings(settings),
        MyCustomStage.from_settings(settings),  # Add your stage
        FactAtomizationStage.from_settings(settings),
        # ... other stages
    ],
    name="document_processing"
)
```

## Advanced Features

### Conditional Stage Execution

Override `should_skip()` to conditionally skip stages:

```python
class ConditionalStage(BaseStage[dict, dict]):
    def should_skip(self, ctx: StageContext) -> bool:
        # Skip if document is small
        if ctx.get("page_count", 0) < 5:
            return True
        return super().should_skip(ctx)
```

### Custom Error Handling

Override `on_error()` to add custom error handling:

```python
class RobustStage(BaseStage[dict, dict]):
    async def on_error(self, ctx: StageContext, error: Exception) -> None:
        # Log to external service
        await send_to_sentry(error)

        # Call parent
        await super().on_error(ctx, error)
```

### Pre/Post Execution Hooks

```python
class HookedStage(BaseStage[dict, dict]):
    async def pre_execute(self, ctx: StageContext) -> None:
        self.logger.info("Setting up stage...")
        # Setup logic

    async def post_execute(self, ctx: StageContext, result: dict) -> None:
        self.logger.info("Cleaning up stage...")
        # Cleanup logic
```

### Custom Caching Logic

```python
class CachedStage(BaseStage[dict, dict]):
    async def execute(self, ctx: StageContext, input_data: dict) -> dict:
        if self.config.cache_enabled:
            # Custom cache key
            cache_key = f"{ctx.document_id}_{input_data['hash']}"

            # Check cache
            cached = await my_cache.get(cache_key)
            if cached:
                return cached

            # Process
            result = await self._process(input_data)

            # Store in cache
            await my_cache.set(cache_key, result)

            return result

        return await self._process(input_data)
```

## Best Practices

1. **Stage Independence**: Each stage should be self-contained and not depend on implementation details of other stages
2. **Use Context**: Pass data between stages via `ctx.set()` and `ctx.get()` instead of global variables
3. **Configuration Over Code**: Use `custom_params` for stage-specific settings instead of hardcoding values
4. **Fail Fast**: Raise `ProcessingError` for unrecoverable errors
5. **Logging**: Use `self.logger` for consistent logging
6. **Type Hints**: Use proper type hints for `TInput` and `TOutput`
7. **Caching**: Enable caching for idempotent stages (OCR, fact extraction, Q&A generation)
8. **Parallelization**: Only enable for stages that can safely run in parallel (web verification, OCR pages)

## Migration from Old System

The old stage functions (`stage_a_ocr.py`, `stage_b_facts.py`, etc.) have been refactored into class-based stages. The new system is backward compatible through the `processing_new.py` file.

To migrate:

1. Update imports in `processing.py`:
   ```python
   from app.worker.tasks.processing_new import process_message_task, create_document_pipeline
   ```

2. Or use the new processing module directly:
   ```python
   from app.worker.tasks import processing_new as processing
   ```

3. All existing functionality is preserved, but now fully modular and configurable!

## Testing

### Unit Testing Stages

```python
import pytest
from app.worker.pipeline.base import StageContext, StageConfig
from app.worker.pipeline.stages import OCRStage

@pytest.mark.asyncio
async def test_ocr_stage():
    config = StageConfig(
        name="ocr_test",
        enabled=True,
        cache_enabled=False  # Disable cache for testing
    )

    stage = OCRStage(config)
    ctx = StageContext(document_id=UUID("..."))

    result = await stage.execute(ctx, None)

    assert result["text"] is not None
    assert result["page_count"] > 0
```

### Integration Testing Pipeline

```python
@pytest.mark.asyncio
async def test_full_pipeline():
    settings = get_settings()
    pipeline = create_document_pipeline(settings)

    result = await pipeline.execute_for_document(
        document_id=test_document_id,
        message_id=test_message_id,
        chat_id=test_chat_id
    )

    assert result["status"] == "completed"
```

## Performance Monitoring

Each stage execution is logged with timing information. Monitor logs for:
- Stage execution time
- Cache hit/miss rates
- Retry counts
- Error rates

Example log output:
```
INFO: Running stage 'ocr_extraction' for document abc-123
INFO: Cache MISS for document abc-123
INFO: OCR completed in 2.3s
INFO: Stage 'ocr_extraction' completed successfully (1/1 attempts)
```

## Troubleshooting

### Stage Failing Repeatedly
- Check `max_retries` configuration
- Review error logs for root cause
- Consider enabling `skip_on_error` for non-critical stages

### Cache Not Working
- Verify `cache_enabled=True` in stage config
- Check cache service is running (Redis/similar)
- Review cache key generation logic

### Pipeline Not Resuming
- Ensure document state is correctly updated
- Verify state-to-stage mapping in `PipelineManager.find_start_index()`
- Check that stage names match expected values

## Future Enhancements

Potential improvements to the pipeline architecture:
- **Conditional branching**: Allow stages to conditionally execute different paths
- **Stage dependencies**: Explicit dependency declaration between stages
- **Pipeline visualization**: Generate visual representation of pipeline execution
- **Metrics collection**: Built-in metrics for monitoring and alerting
- **Stage checkpointing**: Save intermediate results for long-running pipelines
