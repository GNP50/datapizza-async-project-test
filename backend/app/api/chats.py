from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from pydantic import BaseModel
import logging

from app.services.database import get_db
from app.models.user import User
from app.models.chat import Chat
from app.models.message import Message
from app.core.security import get_current_user
from app.schemas.chat import ChatCreate, ChatUpdate, ChatResponse
from app.services.vector import chat_index_manager
from app.services.cleanup_manager import cleanup_manager
from app.services.cache import cache_manager
from app.services.cache_decorator import cache_response
from app.utils.pagination import paginate_query, add_pagination_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


class SearchResult(BaseModel):
    chat: ChatResponse
    score: float

    class Config:
        from_attributes = True


@router.get("", response_model=list[ChatResponse])
async def list_chats(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int | None = Query(None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=100, description="Items per page")
):
    query = select(Chat).where(Chat.user_id == current_user.id).order_by(Chat.updated_at.desc())
    chats, total_count = await paginate_query(db, query, page, page_size)

    if page is not None and page_size is not None:
        add_pagination_headers(response, page, page_size, total_count)

    return chats


@router.get("/search", response_model=list[SearchResult])
async def search_chats(
    response: Response,
    q: str = Query(..., min_length=1, description="Search query"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int | None = Query(None, ge=1, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=100, description="Items per page"),
    limit: int = Query(20, ge=1, le=100, description="Max results from vector search")
):
    """
    Search chats using Qdrant semantic similarity with user_id filtering.
    Returns chats sorted by relevance score.
    """
    if not q or len(q.strip()) == 0:
        return []

    try:
        # Search in Qdrant with MANDATORY user_id filtering
        qdrant_results = await chat_index_manager.search_chats(
            query=q,
            user_id=current_user.id,
            limit=limit,
            score_threshold=0.3
        )

        if not qdrant_results:
            logger.debug(f"No results found in Qdrant for query: {q}")
            return []

        # Get chat IDs from Qdrant results
        chat_ids = [UUID(r["chat_id"]) for r in qdrant_results]

        # Fetch full chat objects from database
        result = await db.execute(
            select(Chat).where(
                Chat.id.in_(chat_ids),
                Chat.user_id == current_user.id  # Double-check security at DB level
            )
        )
        chats_dict = {chat.id: chat for chat in result.scalars().all()}

        # Build results maintaining Qdrant score order
        results = []
        for qdrant_result in qdrant_results:
            chat_id = UUID(qdrant_result["chat_id"])
            chat = chats_dict.get(chat_id)

            if chat:
                results.append(
                    SearchResult(
                        chat=ChatResponse.model_validate(chat),
                        score=qdrant_result["score"]
                    )
                )

        # Apply pagination
        total_count = len(results)
        if page is not None and page_size is not None:
            add_pagination_headers(response, page, page_size, total_count)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            results = results[start_idx:end_idx]

        logger.debug(f"Found {len(results)} chats for query '{q}' (user {current_user.id})")
        return results

    except Exception as e:
        logger.error(f"Search failed for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search service unavailable"
        )


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    chat_data: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    chat = Chat(
        user_id=current_user.id,
        title=chat_data.title
    )

    db.add(chat)
    await db.commit()
    await db.refresh(chat)

    # Index in Qdrant for semantic search (async, non-blocking)
    try:
        await chat_index_manager.index_chat(
            chat_id=chat.id,
            user_id=chat.user_id,
            title=chat.title,
            summary=chat.summary,
            created_at=chat.created_at
        )
    except Exception as e:
        # Don't fail request if indexing fails - log and continue
        logger.warning(f"Failed to index chat {chat.id} in Qdrant: {e}")

    return chat


@router.get("/{chat_id}", response_model=ChatResponse)
@cache_response(prefix="chat")
async def get_chat(
    chat_id: UUID,
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

    return chat


@router.patch("/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: UUID,
    chat_data: ChatUpdate,
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

    chat.title = chat_data.title
    await db.commit()
    await db.refresh(chat)

    # Invalidate Redis L1 cache entries for this specific chat only
    try:
        await cache_manager.clear_pattern(f"cache:chat:{chat_id}:*")
        logger.debug(f"Invalidated Redis cache for updated chat {chat_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate Redis cache for chat {chat_id}: {e}")

    # Re-index in Qdrant for semantic search
    try:
        await chat_index_manager.index_chat(
            chat_id=chat.id,
            user_id=chat.user_id,
            title=chat.title,
            summary=chat.summary,
            created_at=chat.created_at
        )
    except Exception as e:
        # Don't fail request if indexing fails - log and continue
        logger.warning(f"Failed to re-index chat {chat.id} in Qdrant: {e}")

    return chat


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a chat and all associated data using CleanupManager.

    This comprehensively removes:
    - All messages in the chat
    - All documents associated with messages
    - All facts, flashcards, and cache entries for documents
    - All vectors from Qdrant vectorstore
    - The chat from the chat search index
    - The chat itself from the database
    """
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    logger.info(f"Deleting chat {chat_id} with comprehensive cleanup")

    # Track cleanup statistics
    total_stats = {
        "messages_cleaned": 0,
        "documents_cleaned": 0,
        "total_facts_deleted": 0,
        "total_flashcards_deleted": 0,
        "total_cache_entries_deleted": 0,
        "total_vectors_deleted": 0,
    }

    # 1. Get all messages in the chat
    result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

    # 2. Clean up each message using CleanupManager
    # This will handle all documents, facts, flashcards, cache, and vectors
    for message in messages:
        try:
            message_stats = await cleanup_manager.cleanup_message(
                message_id=message.id,
                db=db,
                delete_message=True,  # Delete the message after cleanup
                delete_subsequent_messages=False,  # We're iterating manually
            )
            total_stats["messages_cleaned"] += 1
            total_stats["documents_cleaned"] += message_stats["documents_cleaned"]
            total_stats["total_facts_deleted"] += message_stats["total_facts_deleted"]
            total_stats["total_flashcards_deleted"] += message_stats["total_flashcards_deleted"]
            total_stats["total_cache_entries_deleted"] += message_stats["total_cache_entries_deleted"]
            total_stats["total_vectors_deleted"] += message_stats["total_vectors_deleted"]
        except Exception as e:
            logger.warning(f"Failed to clean up message {message.id}: {e}")

    # 3. Delete the chat itself from database (cascade will handle remaining relations)
    await db.delete(chat)
    await db.commit()

    # Invalidate Redis L1 cache entries for this specific chat only
    try:
        await cache_manager.clear_pattern(f"cache:chat:{chat_id}:*")
        logger.debug(f"Invalidated Redis cache for deleted chat {chat_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate Redis cache for chat {chat_id}: {e}")

    # 4. Delete from Qdrant chat search index
    try:
        await chat_index_manager.delete_chat(chat_id)
    except Exception as e:
        # Don't fail request if Qdrant deletion fails - log and continue
        logger.warning(f"Failed to delete chat {chat_id} from Qdrant chat index: {e}")

    logger.info(f"Chat {chat_id} deleted successfully. Stats: {total_stats}")
