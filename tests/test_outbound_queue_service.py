from types import SimpleNamespace

from app.services.outbound_queue_service import OutboundQueueService, OutboundStatus
from app.whatsapp.provider import SendResult


class FakeDb:
    def flush(self):
        pass

    def get(self, model, item_id):
        return None


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.sent = []

    def send_message(self, phone, message):
        self.sent.append((phone, message))
        return self.result


def queued_message(attempts=0, max_attempts=3):
    return SimpleNamespace(
        id="outbound-1",
        contact_id="contact-1",
        phone_number="51999999999",
        message_text="hola",
        source=None,
        source_id=None,
        attempts=attempts,
        max_attempts=max_attempts,
        provider=None,
        raw_response=None,
        updated_at=None,
        status=OutboundStatus.PENDING,
        sent_at=None,
        error_message=None,
        locked_at=None,
        next_attempt_at=None,
    )


def test_dispatch_marks_sent():
    provider = FakeProvider(SendResult(True, "fake", raw_response={"id": "1"}))
    queued = queued_message()

    result = OutboundQueueService(FakeDb(), provider).dispatch(queued)

    assert result.success is True
    assert queued.status == OutboundStatus.SENT
    assert queued.attempts == 1
    assert queued.sent_at is not None
    assert queued.next_attempt_at is None


def test_dispatch_retries_until_max_attempts():
    provider = FakeProvider(SendResult(False, "fake", error="bridge down"))
    queued = queued_message(attempts=0, max_attempts=2)

    OutboundQueueService(FakeDb(), provider).dispatch(queued)

    assert queued.status == OutboundStatus.RETRYING
    assert queued.error_message == "bridge down"
    assert queued.next_attempt_at is not None

    OutboundQueueService(FakeDb(), provider).dispatch(queued)

    assert queued.status == OutboundStatus.FAILED
    assert queued.attempts == 2
    assert queued.next_attempt_at is None
