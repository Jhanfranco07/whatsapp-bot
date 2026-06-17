import pytest

from app.services.chatbot_service import ChatbotService
from app.services.intent_classifier import IntentClassifier
from app.services.knowledge_base import KnowledgeBase


@pytest.fixture
def classifier():
    return IntentClassifier()


@pytest.mark.parametrize(
    "message",
    [
        "qué facultades tiene USIL",
        "lista de facultades",
        "facultad de ciencias empresariales",
        "facultad de ingeniería",
        "facultad de salud",
    ],
)
def test_faculty_queries(classifier, message):
    intent, entities = classifier.classify(message)

    assert intent == "consulta_facultades"
    assert entities["classification_source"] in {"rules", "tfidf", "levenshtein_blend"}


@pytest.mark.parametrize(
    "message",
    ["qué carreras tiene USIL", "lista de carreras", "qué puedo estudiar en USIL"],
)
def test_general_career_queries(classifier, message):
    intent, _ = classifier.classify(message)

    assert intent == "consulta_carreras"


@pytest.mark.parametrize(
    ("message", "faculty"),
    [
        ("qué carreras hay en ingeniería", "Facultad de Ingeniería e Inteligencia Artificial"),
        ("carreras de ciencias empresariales", "Facultad de Ciencias Empresariales"),
        ("carreras de salud", "Facultad de Ciencias de la Salud"),
        ("carreras de derecho", "Facultad de Derecho"),
        ("carreras de educación", "Facultad de Educación"),
        ("carreras de hotelería turismo y gastronomía", "Facultad de Administración Hotelera, Turismo y Gastronomía"),
        ("carreras de artes y humanidades", "Facultad de Artes y Humanidades"),
        ("carreras de arquitectura", "Facultad de Arquitectura"),
        ("carreras de comunicación", "Facultad de Comunicación"),
    ],
)
def test_careers_by_faculty(classifier, message, faculty):
    intent, entities = classifier.classify(message)

    assert intent == "consulta_carreras_por_facultad"
    assert entities["facultad"] == faculty


@pytest.mark.parametrize(
    ("message", "career", "faculty"),
    [
        ("a qué facultad pertenece derecho", "Derecho", "Facultad de Derecho"),
        ("sistemas pertenece a qué facultad", "Ingeniería de Sistemas de Información", "Facultad de Ingeniería e Inteligencia Artificial"),
        ("marketing en qué facultad está", "Marketing", "Facultad de Ciencias Empresariales"),
        ("medicina humana pertenece a qué facultad", "Medicina Humana", "Facultad de Ciencias de la Salud"),
        ("arquitectura pertenece a qué facultad", "Arquitectura, Urbanismo y Territorio", "Facultad de Arquitectura"),
    ],
)
def test_faculty_of_career(classifier, message, career, faculty):
    intent, entities = classifier.classify(message)

    assert intent == "consulta_facultad_de_carrera"
    assert entities["career"] == career
    assert entities["facultad"] == faculty


@pytest.mark.parametrize(
    ("message", "career"),
    [
        ("administración", "Administración"),
        ("derecho", "Derecho"),
        ("sistemas", "Ingeniería de Sistemas de Información"),
        ("software", "Ingeniería de Software"),
        ("medicina", "Medicina Humana"),
        ("psicología", "Psicología"),
        ("marketing", "Marketing"),
        ("ciencia de datos", "Ciencia de Datos"),
        ("comunicaciones", "Comunicaciones"),
        ("arquitectura", "Arquitectura, Urbanismo y Territorio"),
        ("educación inicial", "Educación Inicial"),
        ("adminsitracion", "Administración"),
        ("sitemas", "Ingeniería de Sistemas de Información"),
        ("derehco", "Derecho"),
        ("sicologia", "Psicología"),
        ("mecatronica", "Ingeniería Mecatrónica"),
        ("comunicacion", "Comunicaciones"),
    ],
)
def test_career_aliases_and_typos(classifier, message, career):
    intent, entities = classifier.classify(message)

    assert intent == "consulta_carrera_especifica"
    assert entities["career"] == career


def test_knowledge_base_careers_helpers():
    kb = KnowledgeBase()

    assert len(kb.get_all_faculties()) == 9
    assert kb.find_faculty("ingeniería")["nombre"] == "Facultad de Ingeniería e Inteligencia Artificial"
    assert kb.find_career("sitemas")["nombre"] == "Ingeniería de Sistemas de Información"
    assert kb.get_faculty_of_career("derehco")["nombre"] == "Facultad de Derecho"
    assert kb.get_careers_by_faculty("salud")


@pytest.mark.parametrize(
    ("intent", "entities", "expected"),
    [
        ("consulta_facultades", {}, "Ciencias Empresariales"),
        ("consulta_carreras", {}, "carreras de Ingeniería"),
        ("consulta_carreras_por_facultad", {"facultad": "Facultad de Ingeniería e Inteligencia Artificial"}, "Ingeniería de Software"),
        ("consulta_facultad_de_carrera", {"career": "Derecho"}, "Facultad de Derecho"),
        ("consulta_carrera_especifica", {"career": "sistemas"}, "soluciones digitales"),
    ],
)
def test_career_responses_are_controlled(intent, entities, expected):
    reply = ChatbotService().respond(intent, entities).bot_reply

    assert expected in reply
    assert "https://www.usil.edu.pe/" in reply
    assert "asesor" not in reply.lower()
    assert "costo" not in reply.lower()
    assert "duración" not in reply.lower()
    assert len(reply) <= 800


def test_noise_still_silent(classifier):
    intent, entities = classifier.classify("jajaja")

    assert intent == "ruido_conversacional"
    assert entities["should_reply"] is False
