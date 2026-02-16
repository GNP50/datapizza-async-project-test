"""
Pipeline stages for document processing.

This package contains all the pipeline stages that implement the BaseStage pattern.
Each stage is self-contained and configurable via StageConfig.
"""

from app.worker.pipeline.stages.ocr_stage import OCRStage
from app.worker.pipeline.stages.fact_stage import FactAtomizationStage
from app.worker.pipeline.stages.verification_stage import WebVerificationStage
from app.worker.pipeline.stages.qa_stage import QAGenerationStage
from app.worker.pipeline.stages.indexing_stage import VectorIndexingStage


__all__ = [
    "OCRStage",
    "FactAtomizationStage",
    "WebVerificationStage",
    "QAGenerationStage",
    "VectorIndexingStage",
]
