from app.services.chatbot_service import ChatbotService


def test_opt_out_response():
    result = ChatbotService().respond("salir_baja", {})
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
    assert "s/" not in reply
    assert "vacantes" not in reply


def test_contextual_thanks_mentions_last_career():
    reply = ChatbotService().respond(
        "agradecimiento", {}, context={"last_career": "Administración"}
    ).bot_reply
    assert "Administración" in reply
