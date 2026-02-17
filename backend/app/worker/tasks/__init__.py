"""
Celery tasks for document processing.
"""
from app.worker.tasks.processing import process_message_task, process_message

__all__ = ["process_message_task", "process_message"]
