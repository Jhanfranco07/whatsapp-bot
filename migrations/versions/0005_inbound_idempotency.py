"""Agrega idempotencia para mensajes entrantes.

Revision ID: 0005_inbound_idempotency
Revises: 0004_runtime_campaign_controls
Create Date: 2026-06-22
"""
from alembic import op


revision = "0005_inbound_idempotency"
down_revision = "0004_runtime_campaign_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE messages "
        "ADD COLUMN IF NOT EXISTS external_id VARCHAR(180)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_external_id "
        "ON messages (external_id) WHERE external_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_messages_external_id")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS external_id")
