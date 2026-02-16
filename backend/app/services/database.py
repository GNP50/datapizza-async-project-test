from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.models.base import Base


class DatabaseManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not DatabaseManager._initialized:
            self.settings = get_settings()
            self.engine = None
            self.async_session_maker = None
            DatabaseManager._initialized = True

    def _ensure_engine(self):
        if self.engine is None:
            # Use NullPool for Celery workers with asyncio.run()
            # This ensures no connection pooling across event loops
            # Each connection is created fresh and closed immediately
            self.engine = create_async_engine(
                self.settings.database_url,
                echo=self.settings.database_echo,
                poolclass=NullPool,
                pool_pre_ping=True,
            )
            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        self._ensure_engine()
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session() as session:
            yield session

    async def create_tables(self):
        self._ensure_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_tables(self):
        self._ensure_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def close(self):
        if self.engine is not None:
            await self.engine.dispose()


db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session
