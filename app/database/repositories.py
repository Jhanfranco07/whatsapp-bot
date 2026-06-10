from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    AdvisorRequest,
    CampaignMessage,
    Contact,
    Conversation,
    Message,
)
from app.schemas.contact_schema import ContactCreate
from app.utils.phone_utils import normalize_phone


class ContactRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_phone(self, phone: str):
        return self.db.scalar(select(Contact).where(Contact.phone_number == normalize_phone(phone)))

    def create(self, data: ContactCreate):
        contact = Contact(**data.model_dump(exclude={"phone_number"}), phone_number=normalize_phone(data.phone_number))
        self.db.add(contact)
        self.db.flush()
        return contact

    def get_or_create(self, phone: str, **values):
        contact = self.get_by_phone(phone)
        if contact:
            return contact, False
        contact = Contact(phone_number=normalize_phone(phone), **values)
        self.db.add(contact)
        self.db.flush()
        return contact, True

    def list(self):
        return list(self.db.scalars(select(Contact).order_by(Contact.created_at.desc())))

    def campaign_candidates(self):
        return list(
            self.db.scalars(
                select(Contact).where(
                    Contact.opt_out.is_(False),
                    Contact.status.not_in(("SALIR", "NO_INTERESADO")),
                )
            )
        )


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, contact, direction, text, intent=None, entities=None, raw_payload=None):
        message = Message(
            contact_id=contact.id,
            phone_number=contact.phone_number,
            direction=direction,
            message_text=text,
            intent=intent,
            entities=entities,
            raw_payload=raw_payload,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def history(self, contact_id):
        return list(
            self.db.scalars(
                select(Message)
                .where(Message.contact_id == contact_id)
                .order_by(Message.created_at.asc())
            )
        )


def upsert_conversation(db, contact, user_message, bot_message, state, context):
    conversation = db.scalar(select(Conversation).where(Conversation.contact_id == contact.id))
    if not conversation:
        conversation = Conversation(contact_id=contact.id)
        db.add(conversation)
    conversation.last_user_message = user_message
    conversation.last_bot_message = bot_message
    conversation.current_state = state
    conversation.context = {**(conversation.context or {}), **context}
    return conversation


def get_conversation_context(db, contact_id):
    conversation = db.scalar(
        select(Conversation).where(Conversation.contact_id == contact_id)
    )
    return dict(conversation.context or {}) if conversation else {}


def create_campaign_record(db, contact, message, result, campaign_name="campaña_inicial"):
    record = CampaignMessage(
        contact_id=contact.id,
        campaign_name=campaign_name,
        template_name="mensaje_inicial",
        message_text=message,
        status="sent" if result.success else "failed",
        error_message=result.error,
        sent_at=datetime.now(timezone.utc) if result.success else None,
    )
    db.add(record)
    return record


def get_or_create_advisor_request(db, contact, reason):
    pending = db.scalar(
        select(AdvisorRequest).where(
            AdvisorRequest.contact_id == contact.id,
            AdvisorRequest.status.in_(("PENDIENTE", "ASIGNADO")),
        )
    )
    if pending:
        return pending, False
    item = AdvisorRequest(contact_id=contact.id, reason=reason)
    db.add(item)
    db.flush()
    return item, True
