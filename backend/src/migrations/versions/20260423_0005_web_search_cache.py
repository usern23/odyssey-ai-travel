"""Add web_search_cache table for WebSearchTool 24h caching.

Revision ID: 20260423_0005
Revises: 20260423_0004
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '20260423_0005'
down_revision: Union[str, None] = '20260423_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'web_search_cache',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('query_hash', sa.String(length=64), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column(
            'search_context_size',
            sa.String(length=16),
            nullable=False,
            server_default='medium',
        ),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column(
            'citations',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        'ix_web_search_cache_query_hash',
        'web_search_cache',
        ['query_hash'],
        unique=True,
    )
    op.create_index(
        'ix_web_search_cache_created_at',
        'web_search_cache',
        ['created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_web_search_cache_created_at', table_name='web_search_cache')
    op.drop_index('ix_web_search_cache_query_hash', table_name='web_search_cache')
    op.drop_table('web_search_cache')
