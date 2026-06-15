"""Esquema inicial seguro para PostgreSQL.

Revision ID: 0001_esquema_inicial
Revises:
Create Date: 2026-06-15
"""
from alembic import op


revision = "0001_esquema_inicial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id UUID PRIMARY KEY,
            full_name TEXT,
            phone_number VARCHAR(20) NOT NULL UNIQUE,
            school TEXT,
            grade TEXT,
            email TEXT,
            career_interest TEXT,
            source TEXT,
            status VARCHAR(40) NOT NULL DEFAULT 'NUEVO',
            opt_out BOOLEAN NOT NULL DEFAULT FALSE,
            stop_bot BOOLEAN NOT NULL DEFAULT FALSE,
            last_intent VARCHAR(80),
            last_message_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_contacts_phone_number ON contacts (phone_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contacts_status ON contacts (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contacts_opt_out ON contacts (opt_out)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contacts_stop_bot ON contacts (stop_bot)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY,
            contact_id UUID NOT NULL REFERENCES contacts(id),
            phone_number VARCHAR(20) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            channel VARCHAR(30) NOT NULL DEFAULT 'whatsapp',
            message_text TEXT NOT NULL,
            intent VARCHAR(80),
            entities JSONB,
            raw_payload JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_contact_id ON messages (contact_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_phone_number ON messages (phone_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_created_at ON messages (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_contact_created ON messages (contact_id, created_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id UUID PRIMARY KEY,
            contact_id UUID NOT NULL UNIQUE REFERENCES contacts(id),
            current_state VARCHAR(80),
            last_user_message TEXT,
            last_bot_message TEXT,
            pending_action VARCHAR(80),
            context JSONB,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_messages (
            id UUID PRIMARY KEY,
            contact_id UUID NOT NULL REFERENCES contacts(id),
            campaign_name VARCHAR(120),
            template_name VARCHAR(120),
            message_text TEXT NOT NULL,
            status VARCHAR(20) NOT NULL,
            error_message TEXT,
            sent_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_messages_status ON campaign_messages (status)")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS requires_advisor")
    op.execute("DROP TABLE IF EXISTS advisor_requests")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS campaign_messages")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS contacts")
