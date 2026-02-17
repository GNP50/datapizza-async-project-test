"""
Dead Letter Queue implementation for failed tasks.
Stores permanently failed tasks for manual inspection and recovery.
"""
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from app.services.database import db_manager
from app.models.message import Message, ProcessingState
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def send_to_dead_letter_queue(
    task_id: str,
    task_name: str,
    args: tuple,
    kwargs: dict,
    exception: Exception,
    traceback: str
) -> None:
    """
    Store failed task information for later analysis.
    In production, you might want to:
    - Store in a separate Redis list
    - Send to a monitoring service (Sentry, Datadog)
    - Save to a dedicated database table
    - Trigger alerts
    """
    logger.error(
        f"Task permanently failed - Dead Letter Queue\n"
        f"Task ID: {task_id}\n"
        f"Task Name: {task_name}\n"
        f"Args: {args}\n"
        f"Kwargs: {kwargs}\n"
        f"Exception: {exception}\n"
        f"Traceback: {traceback}"
    )

    # If it's a message processing task, mark it as failed in DB
    if task_name == "app.worker.tasks.processing.process_message_task" and args:
        message_id = args[0]
        try:
            async with db_manager.session() as db:
                result = await db.execute(
                    select(Message).where(Message.id == UUID(message_id))
                )
                message = result.scalar_one_or_none()
                if message:
                    message.processing_state = ProcessingState.FAILED
                    message.error_message = f"Permanently failed after max retries: {str(exception)}"
                    await db.commit()
                    logger.info(f"Marked message {message_id} as FAILED in database")
        except Exception as db_error:
            logger.error(f"Failed to update message state in DLQ: {db_error}")

    # TODO: In production, also:
    # - await redis_client.lpush("celery:dead_letter_queue", json.dumps(task_data))
    # - Send notification to admin/monitoring service
    # - Create incident ticket


def setup_dead_letter_handler(celery_app):
    """
    Setup Celery signal handlers for failed tasks.
    Call this during Celery app initialization.
    """
    from celery.signals import task_failure

    @task_failure.connect
    def handle_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **kwds):
        """
        Triggered when a task fails permanently (after all retries).
        """
        import asyncio

        task_name = sender.name if sender else "unknown"
        logger.warning(f"Task {task_name} ({task_id}) failed: {exception}")

        # Check if this is a permanent failure (no more retries)
        if sender and hasattr(sender, 'request'):
            retries = sender.request.retries
            max_retries = sender.max_retries
            if retries >= max_retries:
                logger.error(f"Task {task_name} ({task_id}) permanently failed after {retries} retries")

                # Send to dead letter queue
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                loop.run_until_complete(
                    send_to_dead_letter_queue(
                        task_id=task_id,
                        task_name=task_name,
                        args=args or (),
                        kwargs=kwargs or {},
                        exception=exception,
                        traceback=str(traceback) if traceback else str(einfo)
                    )
                )
