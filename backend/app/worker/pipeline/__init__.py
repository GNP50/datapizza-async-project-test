"""
Modular Pipeline Architecture for Document Processing.

This package provides a flexible, configuration-driven pipeline system
based on the Abstract Base Class (ABC) pattern.

Key Components:
- BaseStage: Abstract base class for all pipeline stages
- StageConfig: Configuration object for stages
- StageContext: Execution context passed between stages
- PipelineManager: Orchestrator for executing stage sequences

Example:
    from app.worker.pipeline import PipelineManager
    from app.worker.pipeline.stages import (
        OCRStage,
        FactAtomizationStage,
        WebVerificationStage,
        QAGenerationStage,
        VectorIndexingStage,
    )
    from app.core.config import get_settings

    settings = get_settings()

    pipeline = PipelineManager([
        OCRStage.from_settings(settings),
        FactAtomizationStage.from_settings(settings),
        WebVerificationStage.from_settings(settings),
        QAGenerationStage.from_settings(settings),
        VectorIndexingStage.from_settings(settings),
    ], name="document_processing")

    result = await pipeline.execute_for_document(document_id, message_id, chat_id)
"""

from app.worker.pipeline.base import (
    BaseStage,
    StageConfig,
    StageContext,
    StageResult,
)
from app.worker.pipeline.manager import PipelineManager


__all__ = [
    "BaseStage",
    "StageConfig",
    "StageContext",
    "StageResult",
    "PipelineManager",
]
