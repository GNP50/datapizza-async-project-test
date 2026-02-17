"""
Worker startup initialization.

Ensures all required resources are initialized before processing tasks.
"""
import logging
from app.services.rag.vectorstore import vectorstore
from app.worker.utils.processing_cache import clear_processing_cache

logger = logging.getLogger(__name__)


def initialize_worker():
    """
    Initialize worker resources at startup.

    This function is called when the worker starts to ensure all required
    resources (like Qdrant collections) are properly initialized before
    any tasks are processed.
    """
    logger.info("Initializing worker resources...")

    try:
        # Clear processing cache (ensures fresh state on worker restart)
        logger.info("Clearing processing cache...")
        clear_processing_cache()
        logger.info("Processing cache cleared")

        # Initialize vectorstore (creates collections if needed)
        logger.info("Initializing vectorstore...")
        vectorstore.initialize()
        logger.info("Vectorstore initialization complete")

        logger.info("Worker initialization complete")
        return True

    except Exception as e:
        logger.error(f"Worker initialization failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to initialize worker: {e}") from e
