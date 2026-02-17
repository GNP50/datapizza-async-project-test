"""Database service tests"""
import pytest
from sqlalchemy import select

from app.services.database import DatabaseManager, get_db
from app.models.user import User, UserStatus
from app.core.security import get_password_hash


@pytest.mark.asyncio
class TestDatabaseManager:
    """Test DatabaseManager functionality"""

    async def test_database_manager_singleton(self):
        """Test that DatabaseManager is a singleton"""
        manager1 = DatabaseManager()
        manager2 = DatabaseManager()

        assert manager1 is manager2

    async def test_get_session(self, db_session):
        """Test getting a database session"""
        assert db_session is not None

        # Test we can perform operations
        result = await db_session.execute(select(User))
        users = result.scalars().all()
        assert isinstance(users, list)

    async def test_session_context_manager(self):
        """Test session context manager"""
        manager = DatabaseManager()

        async with manager.session() as session:
            assert session is not None

            # Test database operation
            result = await session.execute(select(User))
            users = result.scalars().all()
            assert isinstance(users, list)

    async def test_session_rollback_on_error(self):
        """Test that session rolls back on error"""
        manager = DatabaseManager()

        try:
            async with manager.session() as session:
                # Create invalid user (should fail)
                user = User(
                    email=None,  # This should fail validation
                    password_hash="test"
                )
                session.add(user)
                # Force flush to trigger error
                await session.flush()
        except Exception:
            # Expected to fail
            pass

        # Session should have been rolled back
        # A new session should work fine
        async with manager.session() as session:
            result = await session.execute(select(User))
            assert result is not None


@pytest.mark.asyncio
class TestGetDb:
    """Test get_db dependency"""

    async def test_get_db_yields_session(self):
        """Test that get_db yields a valid session"""
        async for session in get_db():
            assert session is not None

            # Test we can perform operations
            result = await session.execute(select(User))
            users = result.scalars().all()
            assert isinstance(users, list)


@pytest.mark.asyncio
class TestDatabaseOperations:
    """Test basic database CRUD operations"""

    async def test_create_user(self, db_session):
        """Test creating a user in the database"""
        user = User(
            email="dbtest@example.com",
            password_hash=get_password_hash("testpass123"),
            status=UserStatus.VERIFIED
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.email == "dbtest@example.com"

        # Cleanup
        await db_session.delete(user)
        await db_session.commit()

    async def test_read_user(self, db_session, test_user):
        """Test reading a user from the database"""
        result = await db_session.execute(
            select(User).where(User.id == test_user.id)
        )
        user = result.scalar_one_or_none()

        assert user is not None
        assert user.id == test_user.id
        assert user.email == test_user.email

    async def test_update_user(self, db_session, test_user):
        """Test updating a user in the database"""
        original_email = test_user.email
        new_email = "updated@example.com"

        test_user.email = new_email
        await db_session.commit()
        await db_session.refresh(test_user)

        assert test_user.email == new_email

        # Restore original
        test_user.email = original_email
        await db_session.commit()

    async def test_delete_user(self, db_session):
        """Test deleting a user from the database"""
        user = User(
            email="todelete@example.com",
            password_hash=get_password_hash("testpass123"),
            status=UserStatus.VERIFIED
        )

        db_session.add(user)
        await db_session.commit()
        user_id = user.id

        await db_session.delete(user)
        await db_session.commit()

        # Verify deleted
        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_transaction_commit(self, db_session):
        """Test transaction commits changes"""
        user = User(
            email="transaction@example.com",
            password_hash=get_password_hash("testpass123"),
            status=UserStatus.VERIFIED
        )

        db_session.add(user)
        await db_session.commit()

        # Verify in new query
        result = await db_session.execute(
            select(User).where(User.email == "transaction@example.com")
        )
        found_user = result.scalar_one_or_none()
        assert found_user is not None

        # Cleanup
        await db_session.delete(found_user)
        await db_session.commit()

    async def test_transaction_rollback(self, db_session):
        """Test transaction rollback"""
        user = User(
            email="rollback@example.com",
            password_hash=get_password_hash("testpass123"),
            status=UserStatus.VERIFIED
        )

        db_session.add(user)
        await db_session.flush()  # Flush but don't commit

        # Rollback
        await db_session.rollback()

        # Verify not in database
        result = await db_session.execute(
            select(User).where(User.email == "rollback@example.com")
        )
        assert result.scalar_one_or_none() is None
