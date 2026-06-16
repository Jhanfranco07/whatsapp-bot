from types import SimpleNamespace

import app.services.conversation_service as module
from app.schemas.webhook_schema import InboundMessage
from app.services.conversation_service import ConversationService


class FakeDb:
    def add(self, item):
        pass

    def flush(self):
        pass

    def commit(self):
        pass


class FakeContacts:
    def __init__(self, contact):
        self.contact = contact

    def get_or_create(self, phone, **values):
        return self.contact, False


class FakeMessages:
    def __init__(self):
        self.rows = []

    def create(self, contact, direction, text, intent=None, entities=None, raw_payload=None):
        self.rows.append((direction, text, intent, entities))


def build_service(monkeypatch, context=None):
    contact = SimpleNamespace(
        id="contact-1",
        full_name=None,
        phone_number="51999999999",
        status="NUEVO",
        opt_out=False,
        stop_bot=False,
        last_intent=None,
        last_message_at=None,
        career_interest=None,
    )
    service = ConversationService(FakeDb())
    service.contacts = FakeContacts(contact)
    service.messages = FakeMessages()
    captured = {}
    monkeypatch.setattr(module, "get_conversation_context", lambda db, contact_id: dict(context or {}))
    monkeypatch.setattr(
        module,
        "upsert_conversation",
        lambda db, contact, user, bot, state, saved_context: captured.update(saved_context),
    )
    return service, contact, captured


def test_presentation_updates_contact_name(monkeypatch):
    service, contact, context = build_service(monkeypatch)
    result = service.process_inbound(
        InboundMessage(phone_number="999999999", message="me llamo fiorella")
    )
    assert contact.full_name == "Fiorella"
    assert contact.status == "RESPONDIO"
    assert context["detected_name"] == "Fiorella"
    assert "Fiorella" in result["bot_reply"]


def test_human_contact_request_only_shares_official_channels(monkeypatch):
    service, contact, context = build_service(
        monkeypatch, {"last_career": "Administración"}
    )
    result = service.process_inbound(
        InboundMessage(phone_number="999999999", message="quiero hablar con un asesor")
    )
    assert contact.status == "PIDIO_CONTACTO"
    assert "canales oficiales" in result["bot_reply"].lower()


def test_opt_out_updates_contact(monkeypatch):
    service, contact, _ = build_service(monkeypatch)
    service.process_inbound(
        InboundMessage(phone_number="999999999", message="ya no quiero mensajes")
    )
    assert contact.opt_out is True
    assert contact.status == "SALIR"
    assert contact.stop_bot is True


def test_stopped_contact_is_saved_without_reply(monkeypatch):
    service, contact, _ = build_service(monkeypatch)
    contact.stop_bot = True
    contact.status = "SALIR"
    result = service.process_inbound(
        InboundMessage(phone_number="999999999", message="hola otra vez")
    )
    assert result["should_reply"] is False
    assert result["bot_reply"] is None
    assert result["intent"] == "bot_detenido"
    assert [row[0] for row in service.messages.rows] == ["inbound"]


def test_conversational_noise_is_saved_without_reply(monkeypatch):
    service, contact, _ = build_service(monkeypatch)
    result = service.process_inbound(
        InboundMessage(phone_number="999999999", message="JAJAJA")
    )
    assert result["intent"] == "ruido_conversacional"
    assert result["should_reply"] is False
    assert result["bot_reply"] is None
    assert contact.stop_bot is False
    assert [row[0] for row in service.messages.rows] == ["inbound"]


def test_conversation_saves_last_three_history_messages(monkeypatch):
    service, _, context = build_service(
        monkeypatch,
        {
            "historial": [
                {"role": "user", "content": "uno"},
                {"role": "assistant", "content": "dos"},
                {"role": "user", "content": "tres"},
            ]
        },
    )
    service.process_inbound(
        InboundMessage(phone_number="999999999", message="hola")
    )
    assert len(context["historial"]) == 3
    assert context["historial"][-2]["content"] == "hola"
    assert context["historial"][-1]["role"] == "assistant"


def test_rate_limit_saves_without_reply(monkeypatch):
    service, _, _ = build_service(monkeypatch)
    service._rate_limiter = module.InMemoryRateLimiter(1, 60)
    service.process_inbound(InboundMessage(phone_number="999999999", message="hola"))

    result = service.process_inbound(
        InboundMessage(phone_number="999999999", message="hola de nuevo")
    )

    assert result["intent"] == "rate_limited"
    assert result["should_reply"] is False


def test_explicit_stop_bypasses_rate_limit(monkeypatch):
    service, contact, _ = build_service(monkeypatch)
    service._rate_limiter = module.InMemoryRateLimiter(1, 60)
    service.process_inbound(InboundMessage(phone_number="999999999", message="hola"))

    result = service.process_inbound(
        InboundMessage(phone_number="999999999", message="ya no quiero mensajes")
    )

    assert result["intent"] == "detener_conversacion"
    assert contact.stop_bot is True
