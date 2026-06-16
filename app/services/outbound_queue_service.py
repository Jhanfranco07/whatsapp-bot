from datetime import datetime, timedelta, timezone

from app.database.repositories import OutboundMessageRepository
from app.whatsapp.sender import get_whatsapp_provider


class OutboundStatus:
    PENDING = "pending"
    RETRYING = "retrying"
    SENT = "sent"
    FAILED = "failed"


class OutboundQueueService:
    def __init__(self, db, provider=None):
        self.db = db
        self.provider = provider or get_whatsapp_provider()
        self.outbound = OutboundMessageRepository(db)

    def enqueue(self, contact, text, source=None, source_id=None, max_attempts=3):
        return self.outbound.create(
            contact,
            text,
            source=source,
            source_id=source_id,
            max_attempts=max_attempts,
        )

    def dispatch(self, queued):
        queued.attempts += 1
        result = self.provider.send_message(queued.phone_number, queued.message_text)
        queued.provider = result.provider
        queued.raw_response = result.raw_response
        queued.updated_at = datetime.now(timezone.utc)
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
        self.db.flush()
        return result

    def dispatch_pending(self, limit=20):
        summary = {"sent": 0, "failed": 0, "retrying": 0, "processed": 0}
        for queued in self.outbound.pending(limit):
            result = self.dispatch(queued)
            summary["processed"] += 1
            if result.success:
                summary["sent"] += 1
            elif queued.status == OutboundStatus.FAILED:
                summary["failed"] += 1
            else:
                summary["retrying"] += 1
            self.db.commit()
        return summary
