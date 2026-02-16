"""Chat API tests"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.chat import Chat


@pytest.fixture
async def test_chat(db_session: AsyncSession, test_user):
    """Create a test chat"""
    chat = Chat(
        user_id=test_user.id,
        title="Test Chat",
        summary="This is a test chat for testing"
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


@pytest.mark.asyncio
class TestChatCRUD:
    """Test Chat CRUD operations"""

    async def test_create_chat(self, client: AsyncClient, auth_headers, db_session: AsyncSession):
        """Test creating a new chat"""
        chat_data = {
            "title": "New Test Chat"
        }

        response = await client.post(
            "/api/v1/chats",
            json=chat_data,
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == chat_data["title"]
        assert "id" in data

        # Cleanup
        result = await db_session.execute(
            select(Chat).where(Chat.id == data["id"])
        )
        chat = result.scalar_one_or_none()
        if chat:
            await db_session.delete(chat)
            await db_session.commit()

    async def test_list_chats(self, client: AsyncClient, auth_headers, test_chat):
        """Test listing user's chats"""
        response = await client.get("/api/v1/chats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Find our test chat
        chat_ids = [chat["id"] for chat in data]
        assert str(test_chat.id) in chat_ids

    async def test_list_chats_with_pagination(self, client: AsyncClient, auth_headers, test_chat):
        """Test listing chats with pagination"""
        response = await client.get(
            "/api/v1/chats?page=1&page_size=10",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Check pagination headers (actual header names may vary)
        assert "X-Page" in response.headers or "x-page" in response.headers
        assert "X-Page-Size" in response.headers or "x-page-size" in response.headers
        # Total count might be X-Total-Items instead of X-Total-Count
        assert ("X-Total-Count" in response.headers or "X-Total-Items" in response.headers or
                "x-total-count" in response.headers or "x-total-items" in response.headers)

    async def test_get_chat_by_id(self, client: AsyncClient, auth_headers, test_chat):
        """Test getting a specific chat"""
        response = await client.get(
            f"/api/v1/chats/{test_chat.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_chat.id)
        assert data["title"] == test_chat.title

    async def test_update_chat(self, client: AsyncClient, auth_headers, test_chat, db_session: AsyncSession):
        """Test updating a chat"""
        update_data = {
            "title": "Updated Chat Title"
        }

        response = await client.patch(
            f"/api/v1/chats/{test_chat.id}",
            json=update_data,
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]

        # Verify in database
        await db_session.refresh(test_chat)
        assert test_chat.title == update_data["title"]

    async def test_delete_chat(self, client: AsyncClient, auth_headers, test_chat, db_session: AsyncSession):
        """Test deleting a chat"""
        chat_id = test_chat.id

        response = await client.delete(
            f"/api/v1/chats/{chat_id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify deleted from database
        result = await db_session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestChatSearch:
    """Test chat search functionality"""

    async def test_search_chats_by_title(self, client: AsyncClient, auth_headers, test_chat):
        """Test searching chats by title"""
        response = await client.get(
            f"/api/v1/chats/search?q={test_chat.title}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            # Should include our test chat
            chat_ids = [result["chat"]["id"] for result in data]
            assert str(test_chat.id) in chat_ids

            # Each result should have a score
            for result in data:
                assert "score" in result
                assert "chat" in result

    async def test_search_chats_empty_query(self, client: AsyncClient, auth_headers):
        """Test search with empty query"""
        response = await client.get(
            "/api/v1/chats/search?q=",
            headers=auth_headers
        )

        # Empty query might return validation error (422) or empty list (200)
        assert response.status_code in [200, 422]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0


@pytest.mark.asyncio
class TestChatAuthorization:
    """Test chat authorization and access control"""

    async def test_cannot_access_other_user_chat(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user
    ):
        """Test that users cannot access other users' chats"""
        from app.models.user import User, UserStatus
        from app.core.security import get_password_hash, create_access_token

        # Create another user
        other_user = User(
            email="otheruser@example.com",
            password_hash=get_password_hash("otherpass123"),
            status=UserStatus.VERIFIED
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # Create a chat for the other user
        other_chat = Chat(
            user_id=other_user.id,
            title="Other User's Chat"
        )
        db_session.add(other_chat)
        await db_session.commit()
        await db_session.refresh(other_chat)

        # Try to access other user's chat with test_user's token
        access_token = create_access_token({"sub": str(test_user.id)})
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await client.get(
            f"/api/v1/chats/{other_chat.id}",
            headers=headers
        )

        assert response.status_code == 404  # Should not be found for this user

        # Cleanup
        await db_session.delete(other_chat)
        await db_session.delete(other_user)
        await db_session.commit()

    async def test_list_chats_unauthorized(self, client: AsyncClient):
        """Test listing chats without authentication"""
        response = await client.get("/api/v1/chats")

        assert response.status_code == 401
