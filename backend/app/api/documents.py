from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional
import os
from pathlib import Path

from app.services.database import get_db
from app.models.user import User
from app.models.chat import Chat
from app.models.document import Document, DocumentProcessingState
from app.models.message import Message, ProcessingState
from app.models.fact import Fact
from app.models.flashcard import Flashcard
from app.core.security import get_current_user
from app.services.storage import storage_manager
from app.worker.tasks.processing import process_message_task
from app.worker.tasks.flashcards import generate_flashcards_task
from app.services.processing_cache_service import processing_cache_service
from app.utils.pagination import paginate_query, add_pagination_headers

router = APIRouter(prefix="/api/v1", tags=["documents"])


# --- Schemas ---

class ReprocessFromStageRequest(BaseModel):
    stage: str  # The pipeline stage key to relaunch from
    enable_web_search: bool | None = None  # Optional: enable web search if relaunching from web_verification


class FactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    content: str
    page_number: Optional[int]
    verification_status: str
    web_source_url: list[str]
    confidence_score: float
    verification_reasoning: Optional[str]
    created_at: datetime

    @field_validator('web_source_url', mode='before')
    @classmethod
    def parse_web_source_url(cls, v):
        """Parse web_source_url from DB (newline-separated string) to list."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Split by newline and filter empty strings
            return [url.strip() for url in v.split('\n') if url.strip()]
        return []


class FlashcardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    front: str
    back: str
    category: Optional[str]
    difficulty: int
    confidence: float
    fact_id: Optional[UUID]
    created_at: datetime


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: UUID
    filename: str
    file_size: int
    mime_type: str
    processed: bool
    processing_state: str
    web_search_enabled: bool
    extracted_content: Optional[str]
    created_at: datetime
    updated_at: datetime
    facts: list[FactResponse] = []


# --- Helpers ---

async def _get_document_with_auth(
    document_id: UUID,
    current_user: User,
    db: AsyncSession
) -> Document:
    """Fetch a document and verify the user owns the parent chat."""
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.facts))
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Verify ownership via chat
    result = await db.execute(
        select(Chat).where(Chat.id == document.chat_id, Chat.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return document


# --- Endpoints ---

@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Download the original document file."""
    document = await _get_document_with_auth(document_id, current_user, db)

    # Check if file exists using storage manager
    if not await storage_manager.exists(document.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on server"
        )

    # Download file content using storage manager
    file_content = await storage_manager.download(document.file_path)

    # Return the file as a download using Response with proper headers
    from fastapi.responses import Response as FastAPIResponse
    return FastAPIResponse(
        content=file_content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"'
        }
    )


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get document details including all extracted facts."""
    document = await _get_document_with_auth(document_id, current_user, db)
    return document


@router.get("/documents/{document_id}/facts", response_model=list[FactResponse])
async def get_document_facts(
    document_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int | None = Query(None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=100, description="Items per page"),
    verification_status: list[str] | None = Query(None, description="Filter by verification status (verified, uncertain, debunked, pending)")
):
    """Get all facts extracted from a document."""
    document = await _get_document_with_auth(document_id, current_user, db)

    query = (
        select(Fact)
        .where(Fact.document_id == document_id)
    )

    # Apply verification status filter if provided
    if verification_status:
        query = query.where(Fact.verification_status.in_(verification_status))

    query = query.order_by(Fact.page_number.asc().nulls_last(), Fact.created_at.asc())

    facts, total_count = await paginate_query(db, query, page, page_size)

    if page is not None and page_size is not None:
        add_pagination_headers(response, page, page_size, total_count)

    return facts


@router.post("/documents/{document_id}/reprocess", response_model=DocumentDetailResponse)
async def reprocess_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reprocess a single document by resetting its state and re-triggering the pipeline.
    Cleans up all existing data (facts, cache, vectors) before reprocessing.
    """
    document = await _get_document_with_auth(document_id, current_user, db)

    # Prevent relaunching if the document is already being processed
    if document.processing_state in DocumentProcessingState.active_states():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is already being processed (state: {document.processing_state.value}). Wait for it to complete or stop it first."
        )

    # Clean up all existing data using cleanup manager
    from app.services.cleanup_manager import cleanup_manager
    await cleanup_manager.cleanup_document(
        document_id=document_id,
        db=db,
        delete_document=False  # Don't delete the document, just clean its data
    )

    # Reset document state
    document.processing_state = DocumentProcessingState.PENDING
    document.processed = False

    # Also reset the parent message and clean up subsequent messages
    if document.message_id:
        result = await db.execute(
            select(Message).where(Message.id == document.message_id)
        )
        message = result.scalar_one_or_none()
        if message:
            # Delete all messages that come after this user message (assistant responses, etc.)
            # This ensures a fresh response will be generated
            await cleanup_manager.cleanup_message(
                message_id=message.id,
                db=db,
                delete_message=False,  # Don't delete the user message itself
                delete_subsequent_messages=True,  # Delete assistant responses and follow-ups
                skip_current_message_documents=True  # Skip cleaning this message's documents (already cleaned above)
            )

            message.processing_state = ProcessingState.PENDING
            await db.commit()

            # Re-trigger processing for THIS document only
            process_message_task.apply_async(args=[str(message.id)], kwargs={"only_document_id": str(document_id)})
    else:
        await db.commit()

    # Re-fetch with facts
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.facts))
    )
    refreshed = result.scalar_one()
    return refreshed


@router.post("/documents/{document_id}/reprocess-from-stage", response_model=DocumentDetailResponse)
async def reprocess_from_stage(
    document_id: UUID,
    body: ReprocessFromStageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Reprocess a document starting from a specific pipeline stage.
    Does NOT clean up cache - reuses cached results where available.
    Only deletes subsequent messages and regenerates the response.
    """
    document = await _get_document_with_auth(document_id, current_user, db)

    # Prevent relaunching if the document is already being processed
    if document.processing_state in DocumentProcessingState.active_states():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document is already being processed (state: {document.processing_state.value}). Wait for it to complete or stop it first."
        )

    # Map stage keys to DocumentProcessingState and define ordering
    stage_order = [
        ("pending", DocumentProcessingState.PENDING),
        ("ocr_extraction", DocumentProcessingState.OCR_EXTRACTION),
        ("fact_atomization", DocumentProcessingState.FACT_ATOMIZATION),
        ("web_verification", DocumentProcessingState.WEB_VERIFICATION),
        ("qa_generation", DocumentProcessingState.QA_GENERATION),
        ("vector_indexing", DocumentProcessingState.VECTOR_INDEXING),
    ]

    # Find the requested stage index
    stage_keys = [s[0] for s in stage_order]
    if body.stage not in stage_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage: {body.stage}. Must be one of: {', '.join(stage_keys)}"
        )

    stage_idx = stage_keys.index(body.stage)

    # Set document state to the target stage to indicate where processing should resume
    # The pipeline will start from this stage and skip earlier completed stages
    # Cache is preserved, so stages will use cached results where available
    target_state = stage_order[stage_idx][1]
    document.processing_state = target_state
    document.processed = False

    # Enable web search if requested (only when relaunching web_verification stage)
    if body.enable_web_search is not None and body.stage == "web_verification":
        document.web_search_enabled = body.enable_web_search

    # Reset parent message and clean up subsequent messages
    if document.message_id:
        result = await db.execute(
            select(Message).where(Message.id == document.message_id)
        )
        message = result.scalar_one_or_none()
        if message:
            # Delete all messages that come after this user message (assistant responses, etc.)
            # This ensures a fresh response will be generated
            from app.services.cleanup_manager import cleanup_manager
            await cleanup_manager.cleanup_message(
                message_id=message.id,
                db=db,
                delete_message=False,  # Don't delete the user message itself
                delete_subsequent_messages=True,  # Delete assistant responses and follow-ups
                skip_current_message_documents=True  # Don't touch this message's documents or their cache
            )

            message.processing_state = ProcessingState.PENDING
            await db.commit()

            # Re-trigger processing for THIS document only
            process_message_task.apply_async(args=[str(message.id)], kwargs={"only_document_id": str(document_id)})
    else:
        await db.commit()

    # Re-fetch with facts
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.facts))
    )
    refreshed = result.scalar_one()
    return refreshed


@router.post("/documents/{document_id}/stop", response_model=DocumentDetailResponse)
async def stop_document_processing(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Stop processing a document by marking it as failed."""
    document = await _get_document_with_auth(document_id, current_user, db)

    processing_states = [
        DocumentProcessingState.PENDING,
        DocumentProcessingState.OCR_EXTRACTION,
        DocumentProcessingState.FACT_ATOMIZATION,
        DocumentProcessingState.WEB_VERIFICATION,
        DocumentProcessingState.QA_GENERATION,
        DocumentProcessingState.VECTOR_INDEXING,
    ]

    if document.processing_state not in processing_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is not currently processing. State: {document.processing_state.value}"
        )

    document.processing_state = DocumentProcessingState.FAILED
    await db.commit()

    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.facts))
    )
    refreshed = result.scalar_one()
    return refreshed


@router.get("/chats/{chat_id}/documents", response_model=list[DocumentDetailResponse])
async def list_chat_documents(
    chat_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int | None = Query(None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=100, description="Items per page")
):
    """Get all documents in a chat with their facts."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    query = (
        select(Document)
        .where(Document.chat_id == chat_id)
        .options(selectinload(Document.facts))
        .order_by(Document.created_at.desc())
    )

    documents, total_count = await paginate_query(db, query, page, page_size)

    if page is not None and page_size is not None:
        add_pagination_headers(response, page, page_size, total_count)

    return documents


# --- Flashcard Endpoints ---

@router.post("/documents/{document_id}/generate-flashcards")
async def generate_flashcards(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Trigger flashcard generation for a document. Runs async via Celery."""
    document = await _get_document_with_auth(document_id, current_user, db)

    if document.processing_state != DocumentProcessingState.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be fully processed before generating flashcards"
        )

    # Trigger async flashcard generation
    generate_flashcards_task.delay(str(document_id))

    return {"status": "generating", "document_id": str(document_id)}


@router.get("/documents/{document_id}/flashcards", response_model=list[FlashcardResponse])
async def get_document_flashcards(
    document_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int | None = Query(None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=100, description="Items per page")
):
    """Get all flashcards generated for a document."""
    await _get_document_with_auth(document_id, current_user, db)

    query = (
        select(Flashcard)
        .where(Flashcard.document_id == document_id)
        .order_by(Flashcard.difficulty.asc(), Flashcard.created_at.asc())
    )

    flashcards, total_count = await paginate_query(db, query, page, page_size)

    if page is not None and page_size is not None:
        add_pagination_headers(response, page, page_size, total_count)

    return flashcards
