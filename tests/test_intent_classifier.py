import pytest

from app.services.intent_classifier import IntentClassifier


@pytest.fixture
def classifier():
    return IntentClassifier()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("hola", "saludo"),
        ("informacion acerca de la admision", "consulta_admision"),
        ("quiero saber de carreras", "consulta_carreras"),
        ("pásame el link", "consulta_portal"),
        ("quiero que me llamen", "consulta_contacto"),
        ("quiero hablar con un asesor", "consulta_contacto"),
        ("gracias", "agradecimiento"),
        ("ya no quiero mensajes", "detener_conversacion"),
        ("JAJAJA", "ruido_conversacional"),
        ("no gracias", "agradecimiento"),
        ("malla de administración", "consulta_malla"),
        ("modalidad de derecho", "consulta_modalidad"),
        ("costos de administración", "consulta_costos"),
        ("en que se diferencia cyberseguridad y analisis de datos", "comparacion_carrera"),
        ("qué es Big Data", "consulta_carrera_especifica"),
        ("dónde queda el campus", "consulta_campus"),
        ("tienen intercambios internacionales", "consulta_internacionalidad"),
        ("sabes zonificar", "fuera_de_alcance"),
        ("hasta luego", "despedida"),
        ("becas", "consulta_becas"),
    ],
)
def test_intents(classifier, message, expected):
    intent, entities = classifier.classify(message)
    assert intent == expected
    assert entities["classification_source"] in {"rules", "tfidf", "levenshtein_blend"}


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("me llamo fiorella", "Fiorella"),
        ("soy jhan", "Jhan"),
        ("mi nombre es jhan franco", "Jhan Franco"),
    ],
)
def test_name_presentation(classifier, message, name):
    intent, entities = classifier.classify(message)
    assert intent == "presentacion_nombre"
    assert entities["name"] == name


@pytest.mark.parametrize(
    ("message", "career"),
    [
        ("adminsitracion", "Administración"),
        ("sitemas", "Ingeniería de Sistemas de Información"),
        ("derehco", "Derecho"),
        ("qué es Big Data", "Ciencia de Datos"),
        ("me interesa cyberseguridad", "Ingeniería en Ciberseguridad"),
    ],
)
def test_career_aliases(classifier, message, career):
    intent, entities = classifier.classify(message)
    assert intent == "consulta_carrera_especifica"
    assert entities["career"] == career


def test_compound_career_and_admission(classifier):
    intent, entities = classifier.classify(
        "quiero informacion sobre administracion y admision"
    )
    assert intent == "consulta_carrera_especifica"
    assert entities["secondary_intents"] == ["consulta_admision"]


def test_false_stop_is_rejected(classifier):
    intent, entities = classifier.classify("no gracias")
    assert intent == "agradecimiento"
    assert entities.get("stop_bot") is not True


def test_explicit_stop_sets_stop_bot(classifier):
    intent, entities = classifier.classify("basta")
    assert intent == "detener_conversacion"
    assert entities["stop_bot"] is True
