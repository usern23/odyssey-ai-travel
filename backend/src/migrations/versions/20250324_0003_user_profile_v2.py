"""Переработка анкеты пользователя: новые поля activity_level, budget_level,
category_preferences, landscape_preferences, food_preferences, accommodation_preference.
Удаление старых: travel_style, budget_preference, primary_interests, preferred_activities,
disliked_activities.

Revision ID: 20250324_0003
Revises: 20250120_0002
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20250324_0003'
down_revision: Union[str, None] = '20250120_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Маппинг старых значений → новые
TRAVEL_STYLE_TO_ACTIVITY = {
    'relaxed': 'calm',
    'balanced': 'moderate',
    'fast_paced': 'active',
}

BUDGET_TO_LEVEL = {
    'budget': 'economy',
    'mid_range': 'comfort',
    'luxury': 'unlimited',
}


def upgrade() -> None:
    # 1. Создаём новые enum типы
    op.execute("CREATE TYPE activity_level_enum AS ENUM ('calm', 'moderate', 'active')")
    op.execute("CREATE TYPE budget_level_enum AS ENUM ('economy', 'comfort', 'unlimited')")
    op.execute("CREATE TYPE accommodation_preference_enum AS ENUM ('hostel', 'hotel', 'apartment')")

    # 2. Добавляем новые колонки
    op.add_column('user_profiles', sa.Column(
        'activity_level',
        postgresql.ENUM('calm', 'moderate', 'active', name='activity_level_enum', create_type=False),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'budget_level',
        postgresql.ENUM('economy', 'comfort', 'unlimited', name='budget_level_enum', create_type=False),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'category_preferences',
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'landscape_preferences',
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'food_preferences',
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'accommodation_preference',
        postgresql.ENUM('hostel', 'hotel', 'apartment', name='accommodation_preference_enum', create_type=False),
        nullable=True))

    # 3. Мигрируем данные из старых колонок
    for old_val, new_val in TRAVEL_STYLE_TO_ACTIVITY.items():
        op.execute(sa.text(
            f"UPDATE user_profiles SET activity_level = '{new_val}' "
            f"WHERE travel_style = '{old_val}'"
        ))

    for old_val, new_val in BUDGET_TO_LEVEL.items():
        op.execute(sa.text(
            f"UPDATE user_profiles SET budget_level = '{new_val}' "
            f"WHERE budget_preference = '{old_val}'"
        ))

    # Дефолты для новых колонок
    # Используем jsonb_build_object чтобы избежать проблем с парсингом ':' в sa.text()
    cat_keys = ['museum', 'landmark', 'park', 'restaurant', 'cafe', 'religious',
                'entertainment', 'shopping', 'nightlife', 'nature', 'viewpoint', 'beach']
    cat_args = ', '.join(f"'{k}', 5" for k in cat_keys)
    default_cats_sql = f"jsonb_build_object({cat_args})"

    land_keys = ['sea', 'mountains', 'city', 'village', 'forest', 'desert']
    land_args = ', '.join(f"'{k}', 5" for k in land_keys)
    default_landscape_sql = f"jsonb_build_object({land_args})"

    # Для server_default нужны литеральные JSON строки
    default_cats = '{"museum":5,"landmark":5,"park":5,"restaurant":5,"cafe":5,"religious":5,"entertainment":5,"shopping":5,"nightlife":5,"nature":5,"viewpoint":5,"beach":5}'
    default_landscape = '{"sea":5,"mountains":5,"city":5,"village":5,"forest":5,"desert":5}'

    op.execute(sa.text(f"UPDATE user_profiles SET category_preferences = {default_cats_sql} WHERE category_preferences IS NULL"))
    op.execute(sa.text(f"UPDATE user_profiles SET landscape_preferences = {default_landscape_sql} WHERE landscape_preferences IS NULL"))
    op.execute(sa.text("UPDATE user_profiles SET food_preferences = jsonb_build_object() WHERE food_preferences IS NULL"))
    op.execute(sa.text("UPDATE user_profiles SET activity_level = 'moderate' WHERE activity_level IS NULL"))
    op.execute(sa.text("UPDATE user_profiles SET budget_level = 'comfort' WHERE budget_level IS NULL"))

    # 4. Делаем NOT NULL после заполнения
    op.alter_column('user_profiles', 'activity_level', nullable=False)
    op.alter_column('user_profiles', 'budget_level', nullable=False)
    op.alter_column('user_profiles', 'category_preferences', nullable=False,
                    server_default=sa.text(default_cats_sql))
    op.alter_column('user_profiles', 'landscape_preferences', nullable=False,
                    server_default=sa.text(default_landscape_sql))
    op.alter_column('user_profiles', 'food_preferences', nullable=False,
                    server_default=sa.text("jsonb_build_object()"))

    # 5. Удаляем старые колонки
    op.drop_column('user_profiles', 'travel_style')
    op.drop_column('user_profiles', 'budget_preference')
    op.drop_column('user_profiles', 'primary_interests')
    op.drop_column('user_profiles', 'preferred_activities')
    op.drop_column('user_profiles', 'disliked_activities')

    # 6. Удаляем старые enum типы
    op.execute("DROP TYPE IF EXISTS travel_style_enum")
    op.execute("DROP TYPE IF EXISTS budget_preference_enum")


def downgrade() -> None:
    # Воссоздаём старые enum типы
    op.execute("CREATE TYPE travel_style_enum AS ENUM ('relaxed', 'fast_paced', 'balanced')")
    op.execute("CREATE TYPE budget_preference_enum AS ENUM ('budget', 'mid_range', 'luxury')")

    # Добавляем старые колонки
    op.add_column('user_profiles', sa.Column(
        'travel_style',
        postgresql.ENUM('relaxed', 'fast_paced', 'balanced', name='travel_style_enum', create_type=False),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'budget_preference',
        postgresql.ENUM('budget', 'mid_range', 'luxury', name='budget_preference_enum', create_type=False),
        nullable=True))
    op.add_column('user_profiles', sa.Column(
        'primary_interests', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.add_column('user_profiles', sa.Column(
        'preferred_activities', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")))
    op.add_column('user_profiles', sa.Column(
        'disliked_activities', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'{}'::jsonb")))

    # Мигрируем обратно
    for new_val, old_val in {'calm': 'relaxed', 'moderate': 'balanced', 'active': 'fast_paced'}.items():
        op.execute(sa.text(f"UPDATE user_profiles SET travel_style = '{old_val}' WHERE activity_level = '{new_val}'"))
    for new_val, old_val in {'economy': 'budget', 'comfort': 'mid_range', 'unlimited': 'luxury'}.items():
        op.execute(sa.text(f"UPDATE user_profiles SET budget_preference = '{old_val}' WHERE budget_level = '{new_val}'"))

    op.execute(sa.text("UPDATE user_profiles SET primary_interests = '{}'::jsonb WHERE primary_interests IS NULL"))
    op.execute(sa.text("UPDATE user_profiles SET preferred_activities = '{}'::jsonb WHERE preferred_activities IS NULL"))
    op.execute(sa.text("UPDATE user_profiles SET disliked_activities = '{}'::jsonb WHERE disliked_activities IS NULL"))

    op.alter_column('user_profiles', 'travel_style', nullable=False)
    op.alter_column('user_profiles', 'budget_preference', nullable=False)
    op.alter_column('user_profiles', 'primary_interests', nullable=False)
    op.alter_column('user_profiles', 'preferred_activities', nullable=False)
    op.alter_column('user_profiles', 'disliked_activities', nullable=False)

    # Удаляем новые колонки
    op.drop_column('user_profiles', 'activity_level')
    op.drop_column('user_profiles', 'budget_level')
    op.drop_column('user_profiles', 'category_preferences')
    op.drop_column('user_profiles', 'landscape_preferences')
    op.drop_column('user_profiles', 'food_preferences')
    op.drop_column('user_profiles', 'accommodation_preference')

    op.execute("DROP TYPE IF EXISTS activity_level_enum")
    op.execute("DROP TYPE IF EXISTS budget_level_enum")
    op.execute("DROP TYPE IF EXISTS accommodation_preference_enum")
