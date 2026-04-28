from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.infrastructure.db.base import Base


class WebSearchCache(Base):
    """Persistent cache for WebSearchTool calls.

    Key is a sha256 hash of `(model, search_context_size, query)` so identical
    queries against the same model/context reuse previous results for up to 24h.
    """

    __tablename__ = 'web_search_cache'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    search_context_size: Mapped[str] = mapped_column(String(16), nullable=False, default='medium')
    content: Mapped[str] = mapped_column(Text, nullable=False, default='')
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )