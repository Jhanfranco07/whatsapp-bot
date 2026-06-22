"""Agrega configuracion dinamica y controles de campana.

Revision ID: 0004_runtime_campaign_controls
Revises: 0003_outbound_scheduler
Create Date: 2026-06-22
"""
from alembic import op


revision = "0004_runtime_campaign_controls"
down_revision = "0003_outbound_scheduler"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE campaign_messages "
        "ADD COLUMN IF NOT EXISTS interval_seconds INTEGER NOT NULL DEFAULT 60"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_settings (
            key VARCHAR(80) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS runtime_settings")
    op.execute("ALTER TABLE campaign_messages DROP COLUMN IF EXISTS interval_seconds")
