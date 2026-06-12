import pytest
import asyncio

from app.services.chatbot_service import ChatbotService


def test_opt_out_response():
    result = ChatbotService().respond("salir_baja", {})
    assert result.opt_out is True
    assert result.new_status == "SALIR"


def test_stop_conversation_response():
    result = ChatbotService().respond("detener_conversacion", {})
    assert result.opt_out is True
    assert result.new_status == "SALIR"


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


def test_beca_response_does_not_invent_values():
    reply = ChatbotService().respond("consulta_becas", {}).bot_reply.lower()
    assert "portal" in reply
    assert "%" not in reply
    assert "s/" not in reply


def test_name_presentation_is_friendly():
    result = ChatbotService().respond("presentacion_nombre", {"name": "Fiorella"})
    assert "Fiorella" in result.bot_reply
    assert "Mucho gusto" in result.bot_reply or "Encantado" in result.bot_reply
    assert result.new_status == "RESPONDIO"


def test_known_name_personalizes_greeting():
    contact = type("Contact", (), {"full_name": "Fiorella Tinoco Vega"})()
    reply = ChatbotService().respond("saludo", {}, contact).bot_reply
    assert "Fiorella" in reply


def test_compound_response_mentions_admission_once():
    reply = ChatbotService().respond(
        "consulta_carrera_especifica",
        {
            "career": "Administración",
            "secondary_intents": ["consulta_admision"],
        },
    ).bot_reply
    assert "Administración" in reply
    assert "admisión" in reply
    assert reply.count("https://") == 1


def test_admission_does_not_invent_dates_or_costs():
    reply = ChatbotService().respond("consulta_admision", {}).bot_reply.lower()
    assert "portal" in reply
    assert "s/." not in reply
    assert "vacantes" not in reply


def test_contextual_thanks_mentions_last_career():
    reply = ChatbotService().respond(
        "agradecimiento", {}, context={"last_career": "Administración"}
    ).bot_reply
    assert "Administración" in reply


@pytest.mark.parametrize(
    "intent",
    [
        "comparacion_carrera",
        "consulta_malla",
        "consulta_duracion",
        "consulta_modalidad",
        "consulta_costos",
        "consulta_campus",
        "consulta_internacionalidad",
        "fuera_de_alcance",
        "despedida",
    ],
)
def test_new_intents_have_controlled_responses(intent):
    result = ChatbotService().respond(intent, {})
    assert result.bot_reply
    assert "Intent:" not in result.bot_reply


def test_campus_response_uses_controlled_addresses():
    reply = ChatbotService().respond("consulta_campus", {}).bot_reply
    assert "Av. La Fontana 550" in reply
    assert "Campus Magdalena" in reply


def test_international_response_is_controlled():
    reply = ChatbotService().respond("consulta_internacionalidad", {}).bot_reply
    assert "doble grado" in reply
    assert "portal" in reply


def test_official_career_without_description_uses_safe_response():
    result = ChatbotService().respond(
        "consulta_carrera_especifica", {"career": "Ingeniería Biomédica"}
    )
    assert "Ingeniería Biomédica" in result.bot_reply
    assert "portal de USIL" in result.bot_reply
    assert result.new_status == "INTERESADO_CARRERA"


def test_llm_response_is_used_for_explanatory_intent():
    result = ChatbotService().respond(
        "consulta_campo_laboral",
        {
            "career": "Administración",
            "llm_response": "Respuesta breve generada con contexto controlado.",
            "should_reply": True,
        },
    )
    assert result.bot_reply.startswith("Respuesta breve generada con contexto controlado.")
    assert "https://" in result.bot_reply


def test_llm_response_with_official_link_does_not_repeat_closing():
    response = "Información oficial: https://www.usil.edu.pe/"
    result = ChatbotService().respond(
        "no_entendido",
        {"llm_response": response, "should_reply": True},
    )
    assert result.bot_reply == response


def test_conversational_noise_is_silent():
    result = ChatbotService().respond("ruido_conversacional", {})
    assert result.should_reply is False
    assert result.bot_reply == ""


def test_generate_response_uses_ollama_as_final_writer():
    class WriterLLM:
        async def generate_response(self, user_message, intent, context):
            assert context["carrera_info"]["nombre"] == "Administración"
            assert context["historial"][-1]["content"] == "Me interesa Administración"
            assert context["plantilla_guia"]
            return {
                "response": "Mira, Administración combina gestión y toma de decisiones.",
                "should_reply": True,
            }

    service = ChatbotService(llm_service=WriterLLM())
    reply, should_reply = asyncio.run(
        service.generate_response(
            "consulta_carrera_especifica",
            {"career": "Administración"},
            "contact-1",
            "¿De qué trata?",
            conversation_context={
                "historial": [
                    {"role": "user", "content": "Me interesa Administración"}
                ]
            },
        )
    )
    assert reply.startswith("Mira")
    assert should_reply is True


def test_generate_response_falls_back_when_ollama_fails():
    class FailedWriterLLM:
        async def generate_response(self, user_message, intent, context):
            return {"response": None, "should_reply": True}

    service = ChatbotService(llm_service=FailedWriterLLM())
    reply, should_reply = asyncio.run(
        service.generate_response(
            "consulta_costos",
            {},
            "contact-1",
            "costos",
        )
    )
    assert "costos pueden variar" in reply.lower()
    assert should_reply is True
