from celery import Celery
from celery.signals import worker_ready
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "chatbot_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks.processing", "app.worker.tasks.flashcards"]
)

# Setup Dead Letter Queue handler
from app.worker.utils.dead_letter import setup_dead_letter_handler
setup_dead_letter_handler(celery_app)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_pool="solo",  # Enable async task support

    # Reliability and fault tolerance
    task_acks_late=True,  # ACK only after task completion
    task_reject_on_worker_lost=True,  # Re-queue if worker crashes
    task_acks_on_failure_or_timeout=False,  # Don't ACK failed tasks

    # Retry configuration
    task_autoretry_for=(Exception,),  # Auto-retry on any exception
    task_retry_backoff=True,  # Exponential backoff
    task_retry_backoff_max=600,  # Max 10 minutes
    task_retry_jitter=True,  # Randomize retry times

    # Result backend settings
    result_expires=3600,  # Keep results for 1 hour
    result_persistent=True,  # Persist results

    # Worker prefetch
    worker_prefetch_multiplier=1,  # Fetch one task at a time (better for long tasks)

    # Task events
    task_send_sent_event=True,  # Track task lifecycle
)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """
    Initialize worker resources when the worker is ready.
    This signal is triggered after the worker has started and is ready to accept tasks.
    """
    logger.info("Worker ready signal received, initializing resources...")
    from app.worker.startup import initialize_worker
    try:
        initialize_worker()
        logger.info("Worker initialization successful")
    except Exception as e:
        logger.error(f"Worker initialization failed: {e}", exc_info=True)
        raise
