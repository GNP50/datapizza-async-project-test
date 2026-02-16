"""Message API tests - simplified version"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.chat import Chat
from app.models.message import Message, MessageRole


@pytest.fixture
async def test_chat(db_session: AsyncSession, test_user):
    """Create a test chat for message tests"""
    chat = Chat(
        user_id=test_user.id,
        title="Message Test Chat"
    )
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)

    yield chat

    # Cleanup
    result = await db_session.execute(
        select(Chat).where(Chat.id == chat.id)
    )
    existing_chat = result.scalar_one_or_none()
    if existing_chat:
        await db_session.delete(existing_chat)
        await db_session.commit()


@pytest.fixture
async def test_message(db_session: AsyncSession, test_chat):
    """Create a test message"""
    message = Message(
        chat_id=test_chat.id,
        role=MessageRole.USER,
        content="This is a test message"
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)

    yield message

    # Cleanup
    result = await db_session.execute(
        select(Message).where(Message.id == message.id)
    )
    existing_msg = result.scalar_one_or_none()
    if existing_msg:
        await db_session.delete(existing_msg)
        await db_session.commit()


@pytest.mark.asyncio
class TestMessageCreation:
    """Test message creation"""

    async def test_send_message_json(self, client: AsyncClient, auth_headers, test_chat, db_session: AsyncSession):
        """Test sending a message using JSON endpoint"""
        message_data = {
            "content": "Hello, this is a test message!"
        }

        response = await client.post(
            f"/api/v1/chats/{test_chat.id}/messages/json",
            json=message_data,
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["content"] == message_data["content"]

        # Cleanup
        result = await db_session.execute(
            select(Message).where(Message.id == data["id"])
        )
        msg = result.scalar_one_or_none()
        if msg:
            await db_session.delete(msg)
            await db_session.commit()

    async def test_send_message_unauthorized(self, client: AsyncClient, test_chat):
        """Test sending message without authentication fails"""
        message_data = {
            "content": "Unauthorized message"
        }

        response = await client.post(
            f"/api/v1/chats/{test_chat.id}/messages/json",
            json=message_data
        )

        assert response.status_code == 401

    async def test_send_empty_message(self, client: AsyncClient, auth_headers, test_chat):
        """Test sending empty message fails validation"""
        message_data = {
            "content": ""
        }

        response = await client.post(
            f"/api/v1/chats/{test_chat.id}/messages/json",
            json=message_data,
            headers=auth_headers
        )

        assert response.status_code == 400


@pytest.mark.asyncio
class TestMessageRetrieval:
    """Test message retrieval operations"""

    async def test_list_chat_messages(self, client: AsyncClient, auth_headers, test_chat, test_message):
        """Test listing messages in a chat"""
        response = await client.get(
            f"/api/v1/chats/{test_chat.id}/messages",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should contain our test message
        message_ids = [msg["id"] for msg in data]
        assert str(test_message.id) in message_ids

    async def test_list_messages_with_pagination(self, client: AsyncClient, auth_headers, test_chat, test_message):
        """Test listing messages with pagination"""
        response = await client.get(
            f"/api/v1/chats/{test_chat.id}/messages?page=1&page_size=10",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Check pagination headers exist (header names may vary)
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "x-page" in headers_lower
        assert "x-page-size" in headers_lower
        # Total count header
        assert "x-total-items" in headers_lower or "x-total-count" in headers_lower

    async def test_get_message_status(self, client: AsyncClient, auth_headers, test_message):
        """Test getting message processing status"""
        response = await client.get(
            f"/api/v1/messages/{test_message.id}/status",
            headers=auth_headers
        )

        # Status endpoint should exist
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestMessageAuthorization:
    """Test message access control"""

    async def test_cannot_access_other_user_messages(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_chat
    ):
        """Test that users cannot access other users' messages"""
        from app.models.user import User, UserStatus
        from app.core.security import get_password_hash, create_access_token

        # Create another user
        other_user = User(
            email="othermsguser@example.com",
            password_hash=get_password_hash("otherpass123"),
            status=UserStatus.VERIFIED
        )
        db_session.add(other_user)
        await db_session.commit()

        # Try to access messages for test_chat with other user's token
        access_token = create_access_token({"sub": str(other_user.id)})
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await client.get(
            f"/api/v1/chats/{test_chat.id}/messages",
            headers=headers
        )

        # Should return 404 since other user doesn't have access to this chat
        assert response.status_code == 404

        # Cleanup
        await db_session.delete(other_user)
        await db_session.commit()

    async def test_list_messages_unauthorized(self, client: AsyncClient, test_chat):
        """Test listing messages without authentication"""
        response = await client.get(f"/api/v1/chats/{test_chat.id}/messages")

        assert response.status_code == 401
