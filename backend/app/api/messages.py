import json
import logging
from uuid import UUID

from app.core.security import get_current_user
from app.models.chat import Chat
from app.models.document import Document
from app.models.message import Message, MessageRole, ProcessingState
from app.models.user import User
from app.schemas.chat import (MessageCreate, MessageResponse,
                              MessageStatusResponse)
from app.services.database import get_db
from app.services.storage import generate_file_path, storage_manager
from app.utils.pagination import add_pagination_headers, paginate_query
from app.worker.tasks.processing import process_message_task
from fastapi import (APIRouter, Depends, File, Form, HTTPException, Query,
                     Response, UploadFile, status)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

router = APIRouter(prefix="/api/v1", tags=["messages"])
logger = logging.getLogger(__name__)


class MessageCreateRequest(BaseModel):
    content: str | None = None


@router.post("/chats/{chat_id}/messages/json", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message_json(
    chat_id: UUID,
    request: MessageCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Validate that content is provided
    if not request.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content must be provided for JSON endpoint"
        )

    message = Message(
        chat_id=chat_id,
        role=MessageRole.USER,
        content=request.content,
        processing_state=ProcessingState.PENDING
    )

    db.add(message)
    await db.commit()

    # Re-fetch the message with all relationships eagerly loaded
    result = await db.execute(
        select(Message)
        .where(Message.id == message.id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    refreshed_message = result.scalar_one()

    process_message_task.delay(str(message.id))

    return refreshed_message


@router.post("/chats/{chat_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    chat_id: UUID,
    content: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
    web_search_enabled: str = Form("[]"),  # JSON array of booleans matching files order
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Validate that at least content or files are provided
    if not content and not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either content or files must be provided"
        )

    message = Message(
        chat_id=chat_id,
        role=MessageRole.USER,
        content=content or "",
        processing_state=ProcessingState.PENDING
    )

    db.add(message)
    await db.flush()

    # Parse web_search_enabled flags
    try:
        web_search_flags = json.loads(web_search_enabled)
    except (json.JSONDecodeError, TypeError):
        web_search_flags = []

    if files:
        for idx, file in enumerate(files):
            file_content = await file.read()
            file_path = generate_file_path(
                str(current_user.id),
                str(chat_id),
                str(message.id),
                file.filename
            )

            await storage_manager.upload(file_path, file_content)

            # Get web search flag for this file (default True if not specified)
            web_search_flag = web_search_flags[idx] if idx < len(web_search_flags) else True

            document = Document(
                chat_id=chat_id,
                message_id=message.id,
                filename=file.filename,
                file_path=file_path,
                file_size=len(file_content),
                mime_type=file.content_type or "application/octet-stream",
                processed=False,
                web_search_enabled=web_search_flag
            )
            db.add(document)

    await db.commit()

    # Re-fetch the message with all relationships eagerly loaded
    result = await db.execute(
        select(Message)
        .where(Message.id == message.id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    refreshed_message = result.scalar_one()

    process_message_task.delay(str(message.id))

    return refreshed_message


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message_with_chat(
    content: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Validate that at least content or files are provided
    if not content and not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either content or files must be provided"
        )

    chat = Chat(
        user_id=current_user.id,
        title=content[:50] if content and len(content) > 50 else (content or "New Chat")
    )
    db.add(chat)
    await db.flush()

    message = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=content or "",
        processing_state=ProcessingState.PENDING
    )

    db.add(message)
    await db.flush()

    if files:
        for file in files:
            file_content = await file.read()
            file_path = generate_file_path(
                str(current_user.id),
                str(chat.id),
                str(message.id),
                file.filename
            )

            await storage_manager.upload(file_path, file_content)

            document = Document(
                chat_id=chat.id,
                message_id=message.id,
                filename=file.filename,
                file_path=file_path,
                file_size=len(file_content),
                mime_type=file.content_type or "application/octet-stream",
                processed=False
            )
            db.add(document)

    await db.commit()

    # Re-fetch the message with all relationships eagerly loaded
    result = await db.execute(
        select(Message)
        .where(Message.id == message.id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    refreshed_message = result.scalar_one()

    process_message_task.delay(str(message.id))

    return refreshed_message


@router.get("/chats/{chat_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    chat_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int | None = Query(None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=100, description="Items per page")
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    query = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(
            selectinload(Message.fact_checks),
            selectinload(Message.documents).selectinload(Document.facts)
        )
        .order_by(Message.created_at)
    )

    messages, total_count = await paginate_query(db, query, page, page_size)

    if page is not None and page_size is not None:
        add_pagination_headers(response, page, page_size, total_count)

    return messages


@router.get("/messages/{message_id}/status", response_model=MessageStatusResponse)
async def get_message_status(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Message).where(Message.id == message_id)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    result = await db.execute(
        select(Chat).where(Chat.id == message.chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    return MessageStatusResponse(
        id=message.id,
        processing_state=message.processing_state,
        content=message.content,
        fact_checks=message.fact_checks
    )


class RetryMessageRequest(BaseModel):
    skip_document_processing: bool = False


@router.post("/chats/{chat_id}/messages/{message_id}/retry", response_model=MessageResponse)
async def retry_message(
    chat_id: UUID,
    message_id: UUID,
    request: RetryMessageRequest = RetryMessageRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Retry processing a message by requeuing it.
    Resets the message and its documents to PENDING state and requeues the task.
    When retrying from the chat page, deletes all subsequent messages to avoid confusion.
    Works with messages in any state (failed, completed, etc.).

    Args:
        skip_document_processing: If True, skips document processing and only regenerates the response.
                                  Useful when documents are already processed and you just want a new response.
    """
    # Verify chat ownership
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Get message
    result = await db.execute(
        select(Message)
        .where(Message.id == message_id, Message.chat_id == chat_id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        ).execution_options(populate_existing=True)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Skip retry if already pending or actively being processed (to avoid duplicate tasks)
    if message.processing_state == ProcessingState.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is already pending processing"
        )

    if message.processing_state in ProcessingState.active_states():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Message is currently being processed (state: {message.processing_state.value}). Wait for it to complete or fail before retrying."
        )

    # Use cleanup manager to clean up this message and delete all subsequent messages
    from app.services.cleanup_manager import cleanup_manager

    cleanup_stats = await cleanup_manager.cleanup_message(
        message_id=message_id,
        db=db,
        delete_message=False,  # Don't delete the message itself, we're retrying it
        delete_subsequent_messages=True,  # Delete all messages that come after this one
        skip_current_message_documents=request.skip_document_processing  # Skip cleaning documents if they're already processed
    )

    logger.info(f"Cleanup stats for retry of message {message_id}: {cleanup_stats}")
    logger.info(f"Retry requested with skip_document_processing={request.skip_document_processing}")

    # Reset message state to PENDING
    message.processing_state = ProcessingState.PENDING

    # Reset document states if they exist (only if NOT skipping document processing)
    if not request.skip_document_processing and message.documents:
        from app.models.document import DocumentProcessingState
        for doc in message.documents:
            doc.processing_state = DocumentProcessingState.PENDING
            doc.processed = False

    await db.commit()

    # Re-fetch the message with all relationships eagerly loaded
    result = await db.execute(
        select(Message)
        .where(Message.id == message.id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    refreshed_message = result.scalar_one()

    # Requeue the processing task with skip_document_processing flag
    process_message_task.delay(
        str(message.id),
        only_document_id=None,
        skip_document_processing=request.skip_document_processing,
        bypass_cache=False
    )

    return refreshed_message


@router.post("/chats/{chat_id}/messages/{message_id}/stop", response_model=MessageResponse)
async def stop_message_processing(
    chat_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Stop processing a message by marking it as failed.
    This prevents further processing and allows the user to retry if needed.
    Also cleans up all associated data (facts, cache, vectors).
    """
    # Verify chat ownership
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Get message with documents
    result = await db.execute(
        select(Message)
        .where(Message.id == message_id, Message.chat_id == chat_id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        ).execution_options(populate_existing=True)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Check if message OR any of its documents are actively being processed
    from app.models.document import DocumentProcessingState

    message_is_active = message.processing_state in ProcessingState.active_states()
    documents_are_active = False

    if message.documents:
        for doc in message.documents:
            if doc.processing_state in DocumentProcessingState.active_states():
                documents_are_active = True
                break

    if not message_is_active and not documents_are_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message and its documents are not currently processing. Message state: {message.processing_state.value}"
        )

    # Use cleanup manager to clean up all data for this message and subsequent messages
    from app.services.cleanup_manager import cleanup_manager

    cleanup_stats = await cleanup_manager.cleanup_message(
        message_id=message_id,
        db=db,
        delete_message=False,  # Don't delete the message itself, just mark it as failed
        delete_subsequent_messages=True  # Delete all messages that come after this one
    )

    logger.info(f"Cleanup stats for message {message_id}: {cleanup_stats}")

    # Mark message as failed to stop processing
    message.processing_state = ProcessingState.FAILED

    # Mark all documents as failed
    if message.documents:
        for doc in message.documents:
            if doc.processing_state in DocumentProcessingState.active_states():
                doc.processing_state = DocumentProcessingState.FAILED

    await db.commit()

    # Re-fetch the message with all relationships eagerly loaded
    result = await db.execute(
        select(Message)
        .where(Message.id == message.id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    refreshed_message = result.scalar_one()

    return refreshed_message


@router.post("/chats/{chat_id}/messages/{message_id}/regenerate", response_model=MessageResponse)
async def regenerate_without_cache(
    chat_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Regenerate an assistant response bypassing the semantic cache.
    Forces RAG-based generation using raw document chunks.
    Only works for assistant messages.
    Deletes all subsequent messages before regenerating.
    """
    # Verify chat ownership
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Get message
    result = await db.execute(
        select(Message)
        .where(Message.id == message_id, Message.chat_id == chat_id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        ).execution_options(populate_existing=True)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Only allow regeneration for assistant messages
    if message.role != MessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only regenerate assistant messages"
        )

    # Get the user message that triggered this response BEFORE cleanup
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .where(Message.role == MessageRole.USER)
        .where(Message.created_at < message.created_at)
        .order_by(Message.created_at.desc())
        .limit(1)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    user_message = result.scalar_one_or_none()

    if not user_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot find original user message"
        )

    # Clean up the assistant message and all subsequent messages
    from app.services.cleanup_manager import cleanup_manager

    cleanup_stats = await cleanup_manager.cleanup_message(
        message_id=message_id,
        db=db,
        delete_message=True,  # Delete the assistant message, it will be regenerated
        delete_subsequent_messages=True,  # Delete all messages that come after this one
        skip_current_message_documents=True  # Don't clean the current message's documents (it doesn't have any)
    )

    logger.info(f"Cleanup stats for regenerate of message {message_id}: {cleanup_stats}")

    # Reset user message state to PENDING to trigger regeneration
    user_message.processing_state = ProcessingState.PENDING

    await db.commit()

    # Re-fetch the user message with all relationships eagerly loaded
    result = await db.execute(
        select(Message)
        .where(Message.id == user_message.id)
        .options(
            selectinload(Message.documents).selectinload(Document.facts),
            selectinload(Message.fact_checks)
        )
    )
    refreshed_message = result.scalar_one()

    # Requeue the processing task with bypass_cache=True and skip_document_processing=True
    process_message_task.delay(
        str(user_message.id),
        only_document_id=None,
        skip_document_processing=True,  # Don't reprocess documents
        bypass_cache=True  # Bypass semantic cache
    )

    return refreshed_message
