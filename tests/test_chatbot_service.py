import asyncio

import pytest

from app.services.chatbot_service import ChatbotService


def test_opt_out_response():
    result = ChatbotService().respond("detener_conversacion", {})
    assert result.opt_out is True
    assert result.new_status == "SALIR"


def test_noise_is_silent():
    result = ChatbotService().respond("ruido_conversacional", {})
    assert result.should_reply is False
    assert result.bot_reply == ""


def test_advisor_request():
    result = ChatbotService().respond("quiere_asesor", {})
    assert result.requires_advisor is True
    assert result.advisor_request_needed is True


def test_controlled_career_response():
    result = ChatbotService().respond(
        "consulta_carrera_especifica", {"career": "Ingeniería de Sistemas"}
    )
    assert "desarrollo de software" in result.bot_reply
    assert "portal de USIL" in result.bot_reply


def test_compound_response_mentions_admission_once():
    reply = ChatbotService().respond(
        "consulta_carrera_especifica",
        {"career": "Administración", "secondary_intents": ["consulta_admision"]},
    ).bot_reply
    assert "Administración" in reply
    assert "admisión" in reply.lower()


def test_contextual_thanks_mentions_last_career():
    reply = ChatbotService().respond(
        "agradecimiento", {}, context={"last_career": "Administración"}
    ).bot_reply
    assert "Administración" in reply


def test_official_career_without_local_description_is_safe():
    reply = ChatbotService().respond(
        "consulta_carrera_especifica", {"career": "Ingeniería Biomédica"}
    ).bot_reply
    assert "Ingeniería Biomédica" in reply
    assert "portal" in reply


@pytest.mark.parametrize(
    "intent",
    [
        "consulta_malla",
        "consulta_modalidad",
        "consulta_costos",
        "consulta_campus",
        "consulta_internacionalidad",
        "fuera_de_alcance",
        "despedida",
    ],
)
def test_intents_have_static_responses(intent):
    assert ChatbotService().respond(intent, {}).bot_reply


def test_async_generation_removes_emoji_when_user_did_not_use_one():
    reply, should_reply = asyncio.run(
        ChatbotService().generate_response(
            "saludo", {}, "contact-1", "hola", conversation_context={}
        )
    )
    assert should_reply is True
    assert "😊" not in reply
