"""
Chat summary generation task.
Generates semantic summaries of chat conversations for better search.
"""
import logging
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker.celery_app import celery_app
from app.services.database import get_async_session
from app.models.chat import Chat
from app.models.message import Message
from app.services.llm import llm_service
from app.services.vector import chat_index_manager

logger = logging.getLogger(__name__)


@celery_app.task(name="generate_chat_summary", bind=True)
def generate_chat_summary_task(self, chat_id: str):
    """
    Generate a summary for a chat based on its messages.

    Args:
        chat_id: UUID of the chat to summarize
    """
    import asyncio

    try:
        asyncio.run(_generate_chat_summary(UUID(chat_id)))
        logger.info(f"Successfully generated summary for chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to generate summary for chat {chat_id}: {e}", exc_info=True)
        raise


async def _generate_chat_summary(chat_id: UUID):
    """
    Internal async function to generate chat summary.

    Args:
        chat_id: UUID of the chat to summarize
    """
    async for session in get_async_session():
        try:
            # Get chat and its messages
            result = await session.execute(
                select(Chat).where(Chat.id == chat_id)
            )
            chat = result.scalar_one_or_none()

            if not chat:
                logger.warning(f"Chat {chat_id} not found")
                return

            # Get messages for the chat
            messages_result = await session.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(Message.created_at.asc())
            )
            messages = messages_result.scalars().all()

            if not messages:
                logger.info(f"No messages found for chat {chat_id}")
                return

            # Build conversation text (limit to last 20 messages to avoid token limits)
            recent_messages = messages[-20:] if len(messages) > 20 else messages
            conversation = "\n".join([
                f"{msg.role}: {msg.content}"  # Limit each message to 500 chars
                for msg in recent_messages
            ])

            # Generate summary using LLM
            summary_prompt = f"""Generate a concise summary (2-3 sentences) of the following conversation that captures the main topics and themes discussed. Focus on what the conversation is about, not how it went.

Conversation:
{conversation}

Summary:"""

            try:
                summary = await llm_service.generate(
                    prompt=summary_prompt,
                    max_tokens=150,
                    temperature=0.3
                )

                # Update chat with summary
                chat.summary = summary.strip()
                await session.commit()

                logger.info(f"Generated summary for chat {chat_id}: {summary[:100]}...")

            except Exception as e:
                logger.error(f"Failed to generate summary with LLM: {e}")
                # Fallback: use first user message as summary
                user_messages = [m for m in messages if m.role.value == "user"]
                if user_messages:
                    chat.summary = user_messages[0].content
                    await session.commit()
                    logger.info(f"Used fallback summary for chat {chat_id}")

            # Index/re-index chat in Qdrant after summary update
            try:
                await chat_index_manager.index_chat(
                    chat_id=chat.id,
                    user_id=chat.user_id,
                    title=chat.title,
                    summary=chat.summary,
                    created_at=chat.created_at
                )
                logger.info(f"Indexed chat {chat_id} in Qdrant after summary generation")
            except Exception as e:
                # Don't fail the task if indexing fails
                logger.warning(f"Failed to index chat {chat_id} in Qdrant: {e}")

        except Exception as e:
            logger.error(f"Error in _generate_chat_summary: {e}", exc_info=True)
            await session.rollback()
            raise
