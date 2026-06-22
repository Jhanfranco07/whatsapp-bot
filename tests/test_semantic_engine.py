import pytest

from app.services.semantic_engine import get_semantic_engine


@pytest.fixture(scope="module")
def engine():
    return get_semantic_engine()


def test_singleton_is_reused():
    assert get_semantic_engine() is get_semantic_engine()


def test_corpus_has_required_intents(engine):
    assert engine.intents_loaded >= 8


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("cuéntame sobre arquitectura", "consulta_carrera_especifica"),
        ("salidas laborales de psicología", "consulta_campo_laboral"),
        ("cuánto es la pensión", "consulta_costos"),
        ("cómo puedo postulaar", "consulta_admision"),
        ("dónde queda la cede", "consulta_campus"),
        ("cuántos siclos dura", "consulta_malla"),
        ("clases precenciales", "consulta_modalidad"),
        ("necesito un plomero", "fuera_de_alcance"),
    ],
)
def test_corpus_intents(engine, message, intent):
    assert engine.classify(message).intent == intent


@pytest.mark.parametrize("message", ["JAJAJA", "XD", "OK"])
def test_noise_is_silent(engine, message):
    result = engine.classify(message)
    assert result.intent == "ruido_conversacional"
    assert result.should_reply is False


def test_low_score_is_out_of_scope(engine):
    result = engine.classify("qzxv kkk wwww")
    assert result.intent == "fuera_de_alcance"
    assert result.should_reply is False


def test_health_probe(engine):
    result = engine.classify("hola")
    assert result.intent == "saludo"
    assert result.confidence > 0.5
