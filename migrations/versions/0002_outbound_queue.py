"""Agrega cola persistente de mensajes salientes.

Revision ID: 0002_outbound_queue
Revises: 0001_esquema_inicial
Create Date: 2026-06-16
"""
from alembic import op


revision = "0002_outbound_queue"
down_revision = "0001_esquema_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS outbound_messages (
            id UUID PRIMARY KEY,
            contact_id UUID NOT NULL REFERENCES contacts(id),
            phone_number VARCHAR(20) NOT NULL,
            message_text TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            source VARCHAR(40),
            source_id VARCHAR(120),
            provider VARCHAR(40),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            next_attempt_at TIMESTAMP WITH TIME ZONE,
            sent_at TIMESTAMP WITH TIME ZONE,
            error_message TEXT,
            raw_response JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_messages_contact_id ON outbound_messages (contact_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_messages_phone_number ON outbound_messages (phone_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_messages_status ON outbound_messages (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_messages_source ON outbound_messages (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_messages_next_attempt_at ON outbound_messages (next_attempt_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_outbound_messages_created_at ON outbound_messages (created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outbound_messages_status_next_attempt "
        "ON outbound_messages (status, next_attempt_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS outbound_messages")
