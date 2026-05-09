"""One chat = one trip.

* Cleanup orphan empty trips (created by the trip-worker bug where a
  new Trip was always inserted even when the chat already had one).
* Resolve duplicate chat→trip links: if multiple chats point to the
  same trip, keep the most recent and detach the rest.
* Add a partial UNIQUE index on chats.trip_id (WHERE trip_id IS NOT
  NULL) to enforce the 1:1 relationship at the database level.

Revision ID: 20260428_0006
Revises: 20260423_0005
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = '20260428_0006'
down_revision: Union[str, None] = '20260423_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Detach all but the most recent chat for any duplicated trip_id.
    #    (We pick MAX(id) per trip_id and NULL-out the others to avoid
    #    losing chat history.)
    op.execute(
        """
        WITH ranked AS (
            SELECT id, trip_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY trip_id ORDER BY id DESC
                   ) AS rn
            FROM chats
            WHERE trip_id IS NOT NULL
        )
        UPDATE chats SET trip_id = NULL
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
        """
    )

    # 2. Delete orphan empty trips: trips with an empty generated_plan
    #    and no chat pointing at them. These are leftovers from the
    #    pre-fix flow where each agent conversation created a fresh
    #    Trip even when the chat already had one.
    op.execute(
        """
        DELETE FROM trips
        WHERE (generated_plan IS NULL OR generated_plan = '{}'::jsonb)
          AND id NOT IN (
              SELECT trip_id FROM chats WHERE trip_id IS NOT NULL
          );
        """
    )

    # 3. Enforce 1:1 chat ↔ trip at the DB level.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chats_trip_id_not_null
        ON chats (trip_id)
        WHERE trip_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS uq_chats_trip_id_not_null;')
    # Cleanup of orphan trips and chat detachments are NOT reversed —
    # those rows were already broken state and re-creating them would
    # be wrong.
