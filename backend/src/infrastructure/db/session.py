from __future__ import annotations
import asyncio
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.common.configs import settings
from src.infrastructure.db.base import Base  # noqa: F401  — keeps metadata import for side effects

logger = logging.getLogger(__name__)
engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession)


def _run_alembic_upgrade() -> None:
    """Run `alembic upgrade head` programmatically.

    Uses alembic's Python API so migrations apply equally on docker and local runs.
    Executed in a thread via asyncio.to_thread to avoid blocking the event loop.
    """
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[3]  # .../backend
    alembic_ini = backend_root / 'src' / 'alembic.ini'
    if not alembic_ini.exists():
        logger.warning('alembic.ini not found at %s — skipping migrations', alembic_ini)
        return

    cfg = Config(str(alembic_ini))
    # Ensure Alembic uses the same DB URL as the app.
    cfg.set_main_option('sqlalchemy.url', settings.database_url)
    # `script_location` in ini is relative to CWD; force absolute path.
    cfg.set_main_option('script_location', str(backend_root / 'src' / 'migrations'))
    command.upgrade(cfg, 'head')


async def init_models() -> None:
    """Apply database migrations on application startup.

    Replaces the previous `Base.metadata.create_all` approach so that alembic
    is the single source of truth for schema changes.
    """
    if os.getenv('ODYSSEY_SKIP_MIGRATIONS') == '1':
        logger.info('ODYSSEY_SKIP_MIGRATIONS=1 — skipping alembic upgrade')
        return
    logger.info('Applying database migrations (alembic upgrade head)')
    try:
        await asyncio.to_thread(_run_alembic_upgrade)
        logger.info('Database migrations applied successfully')
    except Exception:
        logger.exception('Failed to apply database migrations')
        raise


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
