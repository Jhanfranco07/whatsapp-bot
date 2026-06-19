from datetime import datetime, timedelta, timezone

from uuid import UUID

from app.database.models import CampaignMessage, Contact
from app.config import get_settings
from app.database.repositories import MessageRepository, OutboundMessageRepository
from app.services.contact_states import CAMPAIGN_EXCLUDED_STATES, ContactState
from app.whatsapp.provider import SendResult
from app.whatsapp.sender import get_whatsapp_provider


class OutboundStatus:
    PENDING = "pending"
    RETRYING = "retrying"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutboundPriority:
    CAMPAIGN = 10
    CONVERSATION = 90
    OPT_OUT = 100


class OutboundQueueService:
    def __init__(self, db, provider=None):
        self.db = db
        self.settings = get_settings()
        self.provider = provider or get_whatsapp_provider()
        self.outbound = OutboundMessageRepository(db)
        self.messages = MessageRepository(db)

    def enqueue(
        self,
        contact,
        text,
        source=None,
        source_id=None,
        max_attempts=3,
        priority=OutboundPriority.CAMPAIGN,
        scheduled_at=None,
    ):
        return self.outbound.create(
            contact,
            text,
            source=source,
            source_id=source_id,
            max_attempts=max_attempts,
            priority=priority,
            scheduled_at=scheduled_at,
        )

    def dispatch(self, queued):
        contact = self.db.get(Contact, queued.contact_id)
        if queued.source == "campaign" and contact and (
            contact.opt_out
            or contact.stop_bot
            or contact.status in CAMPAIGN_EXCLUDED_STATES
        ):
            queued.status = OutboundStatus.CANCELLED
            queued.error_message = "contact excluded before dispatch"
            queued.locked_at = None
            self._update_campaign_record(queued)
            self.db.flush()
            return SendResult(False, "system", error=queued.error_message)
        queued.attempts += 1
        result = self.provider.send_message(queued.phone_number, queued.message_text)
        queued.provider = result.provider
        queued.raw_response = result.raw_response
        queued.updated_at = datetime.now(timezone.utc)
        queued.locked_at = None
        if result.success:
            queued.status = OutboundStatus.SENT
            queued.sent_at = datetime.now(timezone.utc)
            queued.error_message = None
            queued.next_attempt_at = None
        else:
            queued.error_message = result.error
            if queued.attempts >= queued.max_attempts:
                queued.status = OutboundStatus.FAILED
                queued.next_attempt_at = None
            else:
                queued.status = OutboundStatus.RETRYING
                queued.next_attempt_at = datetime.now(timezone.utc) + timedelta(
                    minutes=min(30, 2 ** queued.attempts)
                )
        if queued.source == "campaign":
            self._update_campaign_record(queued)
            if result.success and contact:
                self.messages.create(
                    contact,
                    "outbound",
                    queued.message_text,
                    entities={"source": "campaign", "outbound_id": str(queued.id)},
                )
                contact.status = ContactState.CONTACTADO
            elif queued.status == OutboundStatus.FAILED and contact:
                contact.status = ContactState.ERROR_ENVIO
        self.db.flush()
        return result

    def dispatch_pending(self, limit=1):
        summary = {
            "sent": 0,
            "failed": 0,
            "retrying": 0,
            "cancelled": 0,
            "processed": 0,
        }
        for _ in range(limit):
            queued = self.outbound.claim_next(
                self.settings.campaign_minimum_gap_seconds
            )
            if not queued:
                self.db.rollback()
                break
            result = self.dispatch(queued)
            summary["processed"] += 1
            if result.success:
                summary["sent"] += 1
            elif queued.status == OutboundStatus.CANCELLED:
                summary["cancelled"] += 1
            elif queued.status == OutboundStatus.FAILED:
                summary["failed"] += 1
            else:
                summary["retrying"] += 1
            self.db.commit()
        return summary

    def _update_campaign_record(self, queued) -> None:
        if not queued.source_id:
            return
        try:
            record_id = UUID(str(queued.source_id))
        except ValueError:
            return
        record = self.db.get(CampaignMessage, record_id)
        if not record:
            return
        record.status = queued.status
        record.error_message = queued.error_message
        record.sent_at = queued.sent_at
