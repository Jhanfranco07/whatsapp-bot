import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


def now_utc():
    return datetime.now(timezone.utc)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    school: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    career_interest: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="NUEVO", nullable=False, index=True)
    opt_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    stop_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_intent: Mapped[str | None] = mapped_column(String(80))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    messages: Mapped[list["Message"]] = relationship(back_populates="contact")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="contact", uselist=False)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="whatsapp", nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(80))
    entities: Mapped[dict | None] = mapped_column(JSONB)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)

    contact: Mapped[Contact] = relationship(back_populates="messages")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), unique=True, nullable=False)
    current_state: Mapped[str | None] = mapped_column(String(80))
    last_user_message: Mapped[str | None] = mapped_column(Text)
    last_bot_message: Mapped[str | None] = mapped_column(Text)
    pending_action: Mapped[str | None] = mapped_column(String(80))
    context: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    contact: Mapped[Contact] = relationship(back_populates="conversation")


class CampaignMessage(Base):
    __tablename__ = "campaign_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    campaign_name: Mapped[str | None] = mapped_column(String(120))
    template_name: Mapped[str | None] = mapped_column(String(120))
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


Index("ix_messages_contact_created", Message.contact_id, Message.created_at)
