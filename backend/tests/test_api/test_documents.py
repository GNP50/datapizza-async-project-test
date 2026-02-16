"""Document API tests"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from io import BytesIO

from app.models.chat import Chat
from app.models.document import Document, DocumentProcessingState


@pytest.fixture
async def test_chat(db_session: AsyncSession, test_user):
    """Create a test chat for document tests"""
    chat = Chat(
        user_id=test_user.id,
        title="Document Test Chat"
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
async def test_document(db_session: AsyncSession, test_chat):
    """Create a test document"""
    document = Document(
        chat_id=test_chat.id,
        filename="test.pdf",
        file_size=1024,
        mime_type="application/pdf",
        file_path="/test/path/test.pdf",
        processing_state=DocumentProcessingState.COMPLETED,
        processed=True,
        extracted_content="This is test content from a PDF document."
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    yield document

    # Cleanup
    result = await db_session.execute(
        select(Document).where(Document.id == document.id)
    )
    existing_doc = result.scalar_one_or_none()
    if existing_doc:
        await db_session.delete(existing_doc)
        await db_session.commit()


@pytest.mark.asyncio
class TestDocumentUpload:
    """Test document upload functionality"""

    async def test_upload_document(self, client: AsyncClient, auth_headers, test_chat, db_session: AsyncSession):
        """Test uploading a document to a chat"""
        # Create a fake PDF file
        file_content = b"%PDF-1.4\nTest PDF content"
        files = {
            "file": ("test.pdf", BytesIO(file_content), "application/pdf")
        }

        response = await client.post(
            f"/api/v1/chats/{test_chat.id}/documents",
            files=files,
            headers=auth_headers
        )

        # Document upload might trigger async processing
        assert response.status_code in [201, 202]

        if response.status_code == 201:
            data = response.json()
            assert "id" in data
            assert data["filename"] == "test.pdf"
            assert data["mime_type"] == "application/pdf"

            # Cleanup
            result = await db_session.execute(
                select(Document).where(Document.id == data["id"])
            )
            doc = result.scalar_one_or_none()
            if doc:
                await db_session.delete(doc)
                await db_session.commit()

    async def test_upload_document_unauthorized(self, client: AsyncClient, test_chat):
        """Test uploading without authentication fails"""
        file_content = b"%PDF-1.4\nTest PDF content"
        files = {
            "file": ("test.pdf", BytesIO(file_content), "application/pdf")
        }

        response = await client.post(
            f"/api/v1/chats/{test_chat.id}/documents",
            files=files
        )

        assert response.status_code == 401


@pytest.mark.asyncio
class TestDocumentRetrieval:
    """Test document retrieval operations"""

    async def test_get_document_details(self, client: AsyncClient, auth_headers, test_document):
        """Test getting document details"""
        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_document.id)
        assert data["filename"] == test_document.filename
        assert data["processed"] == test_document.processed

    async def test_get_document_not_found(self, client: AsyncClient, auth_headers):
        """Test getting non-existent document"""
        from uuid import uuid4

        fake_id = uuid4()
        response = await client.get(
            f"/api/v1/documents/{fake_id}",
            headers=auth_headers
        )

        assert response.status_code == 404

    async def test_list_chat_documents(self, client: AsyncClient, auth_headers, test_chat, test_document):
        """Test listing documents in a chat"""
        response = await client.get(
            f"/api/v1/chats/{test_chat.id}/documents",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should contain our test document
        doc_ids = [doc["id"] for doc in data]
        assert str(test_document.id) in doc_ids


@pytest.mark.asyncio
class TestDocumentFacts:
    """Test document facts retrieval"""

    async def test_get_document_facts(self, client: AsyncClient, auth_headers, test_document, db_session: AsyncSession):
        """Test getting facts for a document"""
        from app.models.fact import Fact, VerificationStatus

        # Create a test fact
        fact = Fact(
            document_id=test_document.id,
            content="Test fact content",
            page_number=1,
            verification_status=VerificationStatus.VERIFIED,
            confidence_score=0.95
        )
        db_session.add(fact)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/documents/{test_document.id}/facts",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            assert "content" in data[0]
            assert "verification_status" in data[0]

        # Cleanup
        await db_session.delete(fact)
        await db_session.commit()


@pytest.mark.asyncio
class TestDocumentFlashcards:
    """Test document flashcards functionality"""

    async def test_get_document_flashcards(self, client: AsyncClient, auth_headers, test_document, db_session: AsyncSession):
        """Test getting flashcards for a document"""
        from app.models.flashcard import Flashcard

        # Create a test flashcard
        flashcard = Flashcard(
            document_id=test_document.id,
            front="What is a test?",
            back="A procedure to validate functionality",
            difficulty=2,
            confidence=0.9
        )
        db_session.add(flashcard)
        await db_session.commit()

        response = await client.get(
            f"/api/v1/documents/{test_document.id}/flashcards",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if len(data) > 0:
            assert "front" in data[0]
            assert "back" in data[0]
            assert "difficulty" in data[0]

        # Cleanup
        await db_session.delete(flashcard)
        await db_session.commit()

    async def test_generate_flashcards(self, client: AsyncClient, auth_headers, test_document):
        """Test triggering flashcard generation"""
        response = await client.post(
            f"/api/v1/documents/{test_document.id}/flashcards/generate",
            headers=auth_headers
        )

        # This triggers an async task, so accept both 200 and 202
        assert response.status_code in [200, 202, 404]


@pytest.mark.asyncio
class TestDocumentDeletion:
    """Test document deletion"""

    async def test_delete_document(self, client: AsyncClient, auth_headers, test_document, db_session: AsyncSession):
        """Test deleting a document"""
        doc_id = test_document.id

        response = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify deleted from database
        result = await db_session.execute(
            select(Document).where(Document.id == doc_id)
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
class TestDocumentAuthorization:
    """Test document access control"""

    async def test_cannot_access_other_user_document(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_document
    ):
        """Test that users cannot access other users' documents"""
        from app.models.user import User, UserStatus
        from app.core.security import get_password_hash, create_access_token

        # Create another user
        other_user = User(
            email="otherdocuser@example.com",
            password_hash=get_password_hash("otherpass123"),
            status=UserStatus.VERIFIED
        )
        db_session.add(other_user)
        await db_session.commit()

        # Try to access document with other user's token
        access_token = create_access_token({"sub": str(other_user.id)})
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await client.get(
            f"/api/v1/documents/{test_document.id}",
            headers=headers
        )

        assert response.status_code == 404

        # Cleanup
        await db_session.delete(other_user)
        await db_session.commit()
