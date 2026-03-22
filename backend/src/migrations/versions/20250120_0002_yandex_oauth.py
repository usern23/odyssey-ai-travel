from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20250120_0002'
down_revision: Union[str, None] = '20250120_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'yandex_id', sa.String(length=64), nullable=True))
    op.create_index('ix_users_yandex_id', 'users', ['yandex_id'], unique=True)
    op.alter_column('users', 'hashed_password', nullable=True)


def downgrade() -> None:
    op.alter_column('users', 'hashed_password', nullable=False)
    op.drop_index('ix_users_yandex_id', table_name='users')
    op.drop_column('users', 'yandex_id')
