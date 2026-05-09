"""Favorites are now linked to trips, not chats.

The ``favorites`` table is dropped and recreated with a ``trip_id``
foreign key replacing ``chat_id``.  Old favorites (chat-based) are
discarded — per product decision, users will re-add their saved trips.

Revision ID: 20260502_0007
Revises: 20260428_0006
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '20260502_0007'
down_revision: Union[str, None] = '20260428_0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing chat-based favorites table outright.
    op.drop_table('favorites')

    # Recreate with trip_id.
    op.create_table(
        'favorites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('custom_name', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'trip_id', name='uq_user_trip_favorite'),
    )
    op.create_index('ix_favorites_id', 'favorites', ['id'])
    op.create_index('ix_favorites_user_id', 'favorites', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_favorites_user_id', table_name='favorites')
    op.drop_index('ix_favorites_id', table_name='favorites')
    op.drop_table('favorites')
    op.create_table(
        'favorites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('custom_name', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'chat_id', name='uq_user_chat_favorite'),
    )
    op.create_index('ix_favorites_id', 'favorites', ['id'])
    op.create_index('ix_favorites_user_id', 'favorites', ['user_id'])
