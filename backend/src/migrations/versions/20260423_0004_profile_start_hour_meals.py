"""Переработка анкеты: удаляем accommodation_preference, добавляем start_hour и meal_count_per_day.

Revision ID: 20260423_0004
Revises: 20250324_0003
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '20260423_0004'
down_revision: Union[str, None] = '20250324_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop accommodation_preference column and enum type.
    op.drop_column('user_profiles', 'accommodation_preference')
    op.execute("DROP TYPE IF EXISTS accommodation_preference_enum")

    # 2. Add start_hour (7..12) with default 10.
    op.add_column(
        'user_profiles',
        sa.Column('start_hour', sa.Integer(), nullable=False, server_default='10'),
    )
    op.create_check_constraint(
        'ck_user_profiles_start_hour_range',
        'user_profiles',
        'start_hour BETWEEN 7 AND 12',
    )

    # 3. Add meal_count_per_day (1..3) with default 2.
    op.add_column(
        'user_profiles',
        sa.Column('meal_count_per_day', sa.Integer(), nullable=False, server_default='2'),
    )
    op.create_check_constraint(
        'ck_user_profiles_meal_count_range',
        'user_profiles',
        'meal_count_per_day BETWEEN 1 AND 3',
    )


def downgrade() -> None:
    op.drop_constraint('ck_user_profiles_meal_count_range', 'user_profiles', type_='check')
    op.drop_column('user_profiles', 'meal_count_per_day')
    op.drop_constraint('ck_user_profiles_start_hour_range', 'user_profiles', type_='check')
    op.drop_column('user_profiles', 'start_hour')

    op.execute(
        "CREATE TYPE accommodation_preference_enum AS ENUM ('hostel', 'hotel', 'apartment')",
    )
    op.add_column(
        'user_profiles',
        sa.Column(
            'accommodation_preference',
            sa.Enum('hostel', 'hotel', 'apartment', name='accommodation_preference_enum'),
            nullable=True,
        ),
    )
