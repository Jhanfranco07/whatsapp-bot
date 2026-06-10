import pytest

from app.services.intent_classifier import IntentClassifier


@pytest.fixture
def classifier():
    return IntentClassifier()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("hola", "saludo"),
        ("buenas tardes", "saludo"),
        ("informacion acerca de la admision", "consulta_admision"),
        ("admisión", "consulta_admision"),
        ("quiero inscribirme", "consulta_admision"),
        ("quiero info de admsion", "consulta_admision"),
        ("quiero saber de carreras", "consulta_carreras"),
        ("pásame el link", "consulta_portal"),
        ("quiero que me llamen", "quiere_llamada"),
        ("quiero hablar con un asesor", "quiere_asesor"),
        ("gracias", "agradecimiento"),
        ("ya no quiero mensajes", "salir_baja"),
        ("becas", "consulta_becas"),
        ("algo sin pistas claras", "no_entendido"),
    ],
)
def test_intents(classifier, message, expected):
    intent, _ = classifier.classify(message)
    assert intent == expected


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
        ("quiero informacion sobre la carrera de administracion", "Administración"),
        ("quiero informacion sobre la carrera de diseño grafico", "Diseño Gráfico"),
        ("me interesa ingeniería de sistemas", "Ingeniería de Sistemas"),
        ("negocios internacionales", "Negocios Internacionales"),
    ],
)
def test_specific_careers(classifier, message, career):
    intent, entities = classifier.classify(message)
    assert intent == "consulta_carrera_especifica"
    assert entities["career"] == career


def test_compound_career_and_admission(classifier):
    intent, entities = classifier.classify(
        "quiero informacion sobre administracion y admision"
    )
    assert intent == "consulta_carrera_especifica"
    assert entities["career"] == "Administración"
    assert entities["secondary_intents"] == ["consulta_admision"]
