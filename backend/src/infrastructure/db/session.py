from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.common.configs import settings
from src.infrastructure.db.base import Base
logger = logging.getLogger(__name__)
engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession)


async def init_models() -> None:
    logger.info('Database engine initialized (using Alembic for migrations)')


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
