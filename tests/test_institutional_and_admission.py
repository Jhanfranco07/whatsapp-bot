import asyncio

import pytest

from app.schemas.webhook_schema import InboundMessage
from app.services.chatbot_service import ChatbotService
from app.services.intent_classifier import IntentClassifier
from app.services.conversation_service import ConversationService
from app.services.rate_limiter import InMemoryRateLimiter
import app.services.conversation_service as conversation_module


@pytest.fixture
def classifier():
    return IntentClassifier()


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("cuál es la misión de usil", "consulta_mision"),
        ("visión usil", "consulta_vision"),
        ("valores usil", "consulta_valores"),
        ("propósito usil", "consulta_proposito"),
        ("ideario usil", "consulta_ideario"),
        ("modelo educativo usil", "consulta_modelo_educativo"),
        ("qué es onlife", "consulta_onlife"),
        ("modo usil", "consulta_modo_usil"),
        ("competencias sello", "consulta_competencias_sello"),
        ("perfil de egreso", "consulta_perfil_egreso"),
        ("pilares usil", "consulta_pilares"),
        ("responsabilidad social universitaria", "consulta_sostenibilidad"),
        ("laboratorios usil", "consulta_laboratorios"),
    ],
)
def test_institutional_intents(classifier, message, intent):
    detected, entities = classifier.classify(message)

    assert detected == intent
    assert entities["source"] == "conocimiento_institucional"


@pytest.mark.parametrize(
    ("message", "intent", "modalidad"),
    [
        ("qué modalidades de admisión hay", "consulta_modalidades_admision", None),
        ("modalidad regular", "consulta_regular", "regular"),
        ("estoy en quinto de secundaria", "consulta_regular", "regular"),
        ("qué es admisión destacada", "consulta_admision_destacada", "admision_destacada"),
        ("soy tercio superior", "consulta_admision_destacada", "admision_destacada"),
        ("quiero traslado externo", "consulta_traslado_externo", "traslado_externo"),
        ("vengo de un instituto", "consulta_traslado_externo", "traslado_externo"),
        ("soy deportista destacado", "consulta_deportista_destacado", "deportista_destacado_alta_competencia"),
        ("soy deportista de alta competencia", "consulta_deportista_destacado", "deportista_destacado_alta_competencia"),
        ("tengo bachillerato internacional", "consulta_bachillerato_internacional", "bachillerato_internacional"),
        ("qué es pronabec", "consulta_becas_estado_pronabec", "becas_estado_pronabec"),
        ("becas del estado", "consulta_becas_estado_pronabec", "becas_estado_pronabec"),
    ],
)
def test_admission_modality_intents(classifier, message, intent, modalidad):
    detected, entities = classifier.classify(message)

    assert detected == intent
    assert entities["tema"] == "modalidades_admision"
    if modalidad:
        assert entities["modalidad"] == modalidad


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("qué documentos necesito para admisión destacada", "consulta_documentos_modalidad"),
        ("qué beneficios tiene bachillerato internacional", "consulta_beneficios_modalidad"),
        ("quiero convalidar cursos", "consulta_convalidacion"),
        ("cuánto me convalidan", "consulta_convalidacion"),
    ],
)
def test_admission_detail_intents(classifier, message, intent):
    detected, entities = classifier.classify(message)

    assert detected == intent
    assert entities["source"] == "conocimiento_institucional"


def test_institutional_response_uses_official_link_and_not_advisor():
    reply, should_reply = asyncio.run(
        ChatbotService().generate_response(
            "consulta_mision",
            {"source": "conocimiento_institucional"},
            "contact-1",
            "cuál es la misión de usil",
            conversation_context={},
        )
    )

    assert should_reply is True
    assert "Modelo Formativo Onlife" in reply
    assert "https://www.usil.edu.pe/" in reply
    assert "asesor" not in reply.lower()
    assert len(reply) <= 800


def test_admission_discount_response_is_conditioned():
    reply, _ = asyncio.run(
        ChatbotService().generate_response(
            "consulta_beneficios_modalidad",
            {
                "source": "conocimiento_institucional",
                "modalidad": "admision_destacada",
            },
            "contact-1",
            "qué descuento tiene admisión destacada",
            conversation_context={},
        )
    )

    assert "sujeto a términos" in reply.lower()
    assert "https://descubre.usil.edu.pe/landings/pregrado/admision/" in reply
    assert "asesor" not in reply.lower()


def test_convalidacion_response_mentions_evaluation():
    reply, _ = asyncio.run(
        ChatbotService().generate_response(
            "consulta_convalidacion",
            {
                "source": "conocimiento_institucional",
                "modalidad": "traslado_externo",
            },
            "contact-1",
            "quiero convalidar cursos",
            conversation_context={},
        )
    )

    assert "según evaluación" in reply.lower()
    assert "https://descubre.usil.edu.pe/landings/pregrado/admision/" in reply


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
    def create(self, *args, **kwargs):
        return None


def test_fallback_is_limited_and_resets_on_valid_query(monkeypatch):
    contact = type(
        "Contact",
        (),
        {
            "id": "contact-1",
            "full_name": None,
            "phone_number": "51999999999",
            "status": "NUEVO",
            "opt_out": False,
            "stop_bot": False,
            "last_intent": None,
            "last_message_at": None,
            "career_interest": None,
        },
    )()
    saved = {}
    service = ConversationService(FakeDb())
    service._rate_limiter = InMemoryRateLimiter(10, 60)
    service.contacts = FakeContacts(contact)
    service.messages = FakeMessages()
    monkeypatch.setattr(conversation_module, "get_conversation_context", lambda db, contact_id: dict(saved))
    monkeypatch.setattr(conversation_module, "upsert_conversation", lambda db, contact, user, bot, state, context: saved.update(context))

    first = service.process_inbound(InboundMessage(phone_number="999999999", message="qzxv kkk wwww"))
    second = service.process_inbound(InboundMessage(phone_number="999999999", message="qzxv kkk wwww"))
    third = service.process_inbound(InboundMessage(phone_number="999999999", message="qzxv kkk wwww"))
    valid = service.process_inbound(InboundMessage(phone_number="999999999", message="misión usil"))

    assert first["should_reply"] is True
    assert second["should_reply"] is True
    assert third["should_reply"] is False
    assert valid["intent"] == "consulta_mision"
    assert saved["fallback_count"] == 0
