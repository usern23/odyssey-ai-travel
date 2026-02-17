from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision: str = '20250120_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE travel_style_enum AS ENUM ('relaxed', 'fast_paced', 'balanced')")
    op.execute(
        "CREATE TYPE budget_preference_enum AS ENUM ('budget', 'mid_range', 'luxury')")
    op.execute(
        "CREATE TYPE chat_status_enum AS ENUM ('active', 'archived', 'deleted')")
    op.execute(
        "CREATE TYPE message_role_enum AS ENUM ('user', 'assistant', 'system', 'tool')")
    op.create_table(
        'users',
        sa.Column(
            'id',
            sa.Integer(),
            nullable=False),
        sa.Column(
            'email',
            sa.String(
                length=320),
            nullable=False),
        sa.Column(
            'hashed_password',
            sa.String(
                length=1024),
            nullable=False),
        sa.Column(
            'timezone',
            sa.String(
                length=64),
            nullable=False,
            server_default='UTC'),
        sa.Column(
            'created_at',
            sa.DateTime(
                timezone=True),
            nullable=False,
            server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'email',
            name='uq_users_email'))
    op.create_index('ix_users_id', 'users', ['id'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_table(
        'user_profiles',
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey(
                'users.id',
                ondelete='CASCADE'),
            nullable=False),
        sa.Column(
            'travel_style',
            postgresql.ENUM(
                'relaxed',
                'fast_paced',
                'balanced',
                name='travel_style_enum',
                create_type=False),
            nullable=False),
        sa.Column(
            'budget_preference',
            postgresql.ENUM(
                'budget',
                'mid_range',
                'luxury',
                name='budget_preference_enum',
                create_type=False),
            nullable=False),
        sa.Column(
            'primary_interests',
            postgresql.JSONB(
                astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            'preferred_activities',
            postgresql.JSONB(
                astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            'disliked_activities',
            postgresql.JSONB(
                astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            'updated_at',
            sa.DateTime(
                timezone=True),
            nullable=True,
            server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('user_id'))
    op.create_index(
        'ix_user_profiles_user_id',
        'user_profiles',
        ['user_id'],
        unique=True)
    op.create_table(
        'trips', sa.Column(
            'id', sa.Integer(), nullable=False), sa.Column(
            'user_id', sa.Integer(), nullable=False), sa.Column(
                'name', sa.String(
                    length=255), nullable=False), sa.Column(
                        'destination', sa.String(
                            length=255), nullable=True), sa.Column(
                                'origin', sa.String(
                                    length=255), nullable=True), sa.Column(
                                        'start_date', sa.Date(), nullable=True), sa.Column(
                                            'end_date', sa.Date(), nullable=True), sa.Column(
                                                'trip_profile', postgresql.JSONB(
                                                    astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column(
                                                        'generated_plan', postgresql.JSONB(
                                                            astext_type=sa.Text()), nullable=True), sa.Column(
                                                                'created_at', sa.DateTime(
                                                                    timezone=True), nullable=False, server_default=sa.func.now()), sa.Column(
                                                                        'updated_at', sa.DateTime(
                                                                            timezone=True), nullable=False, server_default=sa.func.now()), sa.ForeignKeyConstraint(
                                                                                ['user_id'], ['users.id'], ondelete='CASCADE'), sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_trips_id', 'trips', ['id'], unique=False)
    op.create_index('ix_trips_user_id', 'trips', ['user_id'], unique=False)
    op.create_table(
        'chats',
        sa.Column(
            'id',
            sa.Integer(),
            nullable=False),
        sa.Column(
            'user_id',
            sa.Integer(),
            nullable=False),
        sa.Column(
            'trip_id',
            sa.Integer(),
            nullable=True),
        sa.Column(
            'title',
            sa.String(255),
            nullable=False,
            server_default='Новый чат'),
        sa.Column(
            'status',
            postgresql.ENUM(
                'active',
                'archived',
                'deleted',
                name='chat_status_enum',
                create_type=False),
            nullable=False,
            server_default='active'),
        sa.Column(
            'created_at',
            sa.DateTime(
                timezone=True),
            server_default=sa.func.now(),
            nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(
                timezone=True),
            server_default=sa.func.now(),
            nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['trip_id'],
            ['trips.id'],
            ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_chats_id', 'chats', ['id'])
    op.create_index('ix_chats_user_id', 'chats', ['user_id'])
    op.create_table(
        'chat_messages',
        sa.Column(
            'id',
            sa.Integer(),
            nullable=False),
        sa.Column(
            'chat_id',
            sa.Integer(),
            nullable=False),
        sa.Column(
            'role',
            postgresql.ENUM(
                'user',
                'assistant',
                'system',
                'tool',
                name='message_role_enum',
                create_type=False),
            nullable=False),
        sa.Column(
            'content',
            sa.Text(),
            nullable=False),
        sa.Column(
            'tool_name',
            sa.String(100),
            nullable=True),
        sa.Column(
            'tool_call_id',
            sa.String(100),
            nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(
                timezone=True),
            server_default=sa.func.now(),
            nullable=False),
        sa.ForeignKeyConstraint(
            ['chat_id'],
            ['chats.id'],
            ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_chat_messages_id', 'chat_messages', ['id'])
    op.create_index('ix_chat_messages_chat_id', 'chat_messages', ['chat_id'])
    op.create_table(
        'favorites', sa.Column(
            'id', sa.Integer(), nullable=False), sa.Column(
            'user_id', sa.Integer(), nullable=False), sa.Column(
                'chat_id', sa.Integer(), nullable=False), sa.Column(
                    'custom_name', sa.String(255), nullable=True), sa.Column(
                        'created_at', sa.DateTime(
                            timezone=True), server_default=sa.func.now(), nullable=False), sa.ForeignKeyConstraint(
                                ['user_id'], ['users.id'], ondelete='CASCADE'), sa.ForeignKeyConstraint(
                                    ['chat_id'], ['chats.id'], ondelete='CASCADE'), sa.PrimaryKeyConstraint('id'), sa.UniqueConstraint(
                                        'user_id', 'chat_id', name='uq_user_chat_favorite'))
    op.create_index('ix_favorites_id', 'favorites', ['id'])
    op.create_index('ix_favorites_user_id', 'favorites', ['user_id'])


def downgrade() -> None:
    op.drop_table('favorites')
    op.drop_table('chat_messages')
    op.drop_table('chats')
    op.drop_table('trips')
    op.drop_table('user_profiles')
    op.drop_table('users')
    op.execute('DROP TYPE IF EXISTS message_role_enum')
    op.execute('DROP TYPE IF EXISTS chat_status_enum')
    op.execute('DROP TYPE IF EXISTS budget_preference_enum')
    op.execute('DROP TYPE IF EXISTS travel_style_enum')
