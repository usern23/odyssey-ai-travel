"""Добавляем настраиваемый конец активного дня в профиль.

Revision ID: 20260509_0008
Revises: 20260502_0007
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '20260509_0008'
down_revision: Union[str, None] = '20260502_0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL — означает «вычислить из start_hour + hours_per_day(activity_level)».
    op.add_column(
        'user_profiles',
        sa.Column('end_hour', sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        'ck_user_profiles_end_hour_range',
        'user_profiles',
        'end_hour IS NULL OR end_hour BETWEEN 14 AND 24',
    )
    op.create_check_constraint(
        'ck_user_profiles_end_after_start',
        'user_profiles',
        'end_hour IS NULL OR end_hour - start_hour >= 4',
    )


def downgrade() -> None:
    op.drop_constraint('ck_user_profiles_end_after_start', 'user_profiles', type_='check')
    op.drop_constraint('ck_user_profiles_end_hour_range', 'user_profiles', type_='check')
    op.drop_column('user_profiles', 'end_hour')
