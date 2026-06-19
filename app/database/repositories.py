from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    CampaignMessage,
    Contact,
    Conversation,
    Message,
    OutboundMessage,
)
from app.schemas.contact_schema import ContactCreate
from app.services.contact_states import CAMPAIGN_EXCLUDED_STATES
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
        normalized_phone = normalize_phone(phone)
        try:
            with self.db.begin_nested():
                contact = Contact(phone_number=normalized_phone, **values)
                self.db.add(contact)
                self.db.flush()
            return contact, True
        except IntegrityError:
            contact = self.db.scalar(
                select(Contact).where(Contact.phone_number == normalized_phone)
            )
            if contact:
                return contact, False
            raise

    def list(self):
        return list(self.db.scalars(select(Contact).order_by(Contact.created_at.desc())))

    def campaign_candidates(self, campaign_name="campaña_inicial"):
        already_queued = (
            select(CampaignMessage.id)
            .where(
                CampaignMessage.contact_id == Contact.id,
                CampaignMessage.campaign_name == campaign_name,
                CampaignMessage.status.in_(("pending", "retrying", "sent")),
            )
            .exists()
        )
        return list(
            self.db.scalars(
                select(Contact).where(
                    Contact.opt_out.is_(False),
                    Contact.stop_bot.is_(False),
                    Contact.status.not_in(CAMPAIGN_EXCLUDED_STATES),
                    ~already_queued,
                )
            )
        )

    def has_campaign_record(self, contact_id, campaign_name="campaña_inicial"):
        return bool(
            self.db.scalar(
                select(CampaignMessage.id).where(
                    CampaignMessage.contact_id == contact_id,
                    CampaignMessage.campaign_name == campaign_name,
                    CampaignMessage.status.in_(("pending", "retrying", "sent")),
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


class OutboundMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        contact,
        text,
        source=None,
        source_id=None,
        max_attempts=3,
        priority=10,
        scheduled_at=None,
    ):
        now = datetime.now(timezone.utc)
        queued = OutboundMessage(
            contact_id=contact.id,
            phone_number=contact.phone_number,
            message_text=text,
            status="pending",
            source=source,
            source_id=source_id,
            attempts=0,
            max_attempts=max_attempts,
            priority=priority,
            scheduled_at=scheduled_at or now,
            locked_at=None,
            next_attempt_at=None,
            created_at=now,
            updated_at=now,
        )
        self.db.add(queued)
        self.db.flush()
        return queued

    def pending(self, limit=20):
        now = datetime.now(timezone.utc)
        return list(
            self.db.scalars(
                select(OutboundMessage)
                .where(
                    OutboundMessage.status.in_(("pending", "retrying")),
                    OutboundMessage.scheduled_at <= now,
                    or_(
                        OutboundMessage.next_attempt_at.is_(None),
                        OutboundMessage.next_attempt_at <= now,
                    ),
                    OutboundMessage.attempts < OutboundMessage.max_attempts,
                )
                .order_by(
                    OutboundMessage.priority.desc(),
                    OutboundMessage.scheduled_at.asc(),
                    OutboundMessage.created_at.asc(),
                )
                .limit(limit)
            )
        )

    def claim_next(self, campaign_minimum_gap_seconds=60):
        acquired = self.db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
            {"lock_key": 8675309},
        )
        if not acquired:
            return None
        now = datetime.now(timezone.utc)
        stale_lock = now - timedelta(minutes=5)
        queued = self.db.scalar(
            select(OutboundMessage)
            .where(
                OutboundMessage.status.in_(("pending", "retrying")),
                OutboundMessage.scheduled_at <= now,
                or_(
                    OutboundMessage.next_attempt_at.is_(None),
                    OutboundMessage.next_attempt_at <= now,
                ),
                or_(
                    OutboundMessage.locked_at.is_(None),
                    OutboundMessage.locked_at < stale_lock,
                ),
                OutboundMessage.attempts < OutboundMessage.max_attempts,
            )
            .order_by(
                OutboundMessage.priority.desc(),
                OutboundMessage.scheduled_at.asc(),
                OutboundMessage.created_at.asc(),
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if queued:
            if queued.source == "campaign" and campaign_minimum_gap_seconds > 0:
                last_campaign_sent_at = self.db.scalar(
                    select(OutboundMessage.sent_at)
                    .where(
                        OutboundMessage.source == "campaign",
                        OutboundMessage.status == "sent",
                        OutboundMessage.sent_at.is_not(None),
                    )
                    .order_by(OutboundMessage.sent_at.desc())
                    .limit(1)
                )
                if (
                    last_campaign_sent_at
                    and last_campaign_sent_at
                    + timedelta(seconds=campaign_minimum_gap_seconds)
                    > now
                ):
                    return None
            queued.locked_at = now
            self.db.flush()
        return queued


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


def create_campaign_record(
    db,
    contact,
    message,
    result=None,
    campaign_name="campaña_inicial",
):
    success = bool(result and result.success)
    record = CampaignMessage(
        contact_id=contact.id,
        campaign_name=campaign_name,
        template_name="mensaje_inicial",
        message_text=message,
        status="sent" if success else ("failed" if result else "pending"),
        error_message=result.error if result else None,
        sent_at=datetime.now(timezone.utc) if success else None,
    )
    db.add(record)
    return record
