"""Agrega prioridad y programacion a la cola saliente.

Revision ID: 0003_outbound_scheduler
Revises: 0002_outbound_queue
Create Date: 2026-06-19
"""
from alembic import op


revision = "0003_outbound_scheduler"
down_revision = "0002_outbound_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE outbound_messages "
        "ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 10"
    )
    op.execute(
        "ALTER TABLE outbound_messages "
        "ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "UPDATE outbound_messages SET scheduled_at = COALESCE(next_attempt_at, created_at, NOW()) "
        "WHERE scheduled_at IS NULL"
    )
    op.execute(
        "ALTER TABLE outbound_messages ALTER COLUMN scheduled_at SET DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE outbound_messages ALTER COLUMN scheduled_at SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE outbound_messages "
        "ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_priority "
        "ON outbound_messages (priority)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_scheduled_at "
        "ON outbound_messages (scheduled_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_locked_at "
        "ON outbound_messages (locked_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_dispatch_order "
        "ON outbound_messages (status, priority DESC, scheduled_at, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_dispatch_order")
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_locked_at")
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_scheduled_at")
    op.execute("DROP INDEX IF EXISTS ix_outbound_messages_priority")
    op.execute("ALTER TABLE outbound_messages DROP COLUMN IF EXISTS locked_at")
    op.execute("ALTER TABLE outbound_messages DROP COLUMN IF EXISTS scheduled_at")
    op.execute("ALTER TABLE outbound_messages DROP COLUMN IF EXISTS priority")
