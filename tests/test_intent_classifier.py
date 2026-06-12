import pytest

from app.services.intent_classifier import IntentClassifier


class DisabledLLM:
    def classify(self, message):
        return None


@pytest.fixture
def classifier():
    return IntentClassifier(llm_service=DisabledLLM())


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
        ("ya no quiero mensajes", "detener_conversacion"),
        ("basta", "detener_conversacion"),
        ("JAJAJA", "ruido_conversacional"),
        ("XD", "ruido_conversacional"),
        ("OK", "ruido_conversacional"),
        ("YA", "ruido_conversacional"),
        ("AJA", "ruido_conversacional"),
        ("no gracias", "agradecimiento"),
        ("malla de administración", "consulta_malla"),
        ("cuánto dura sistemas", "consulta_duracion"),
        ("modalidad de derecho", "consulta_modalidad"),
        ("costos de administración", "consulta_costos"),
        ("dónde queda el campus", "consulta_campus"),
        ("tienen intercambios internacionales", "consulta_internacionalidad"),
        ("hablar con Jhan", "quiere_asesor"),
        ("sabes zonificar", "fuera_de_alcance"),
        ("hasta luego", "despedida"),
        ("becas", "consulta_becas"),
        ("algo sin pistas claras", "no_entendido"),
    ],
)
def test_intents(classifier, message, expected):
    intent, entities = classifier.classify(message)
    assert intent == expected
    assert entities["classification_source"] == "rules"


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
    assert entities["classification_source"] == "rules"


@pytest.mark.parametrize(
    ("message", "career"),
    [
        ("quiero informacion sobre la carrera de administracion", "Administración"),
        ("quiero informacion sobre la carrera de diseño grafico", "Diseño Gráfico"),
        ("me interesa ingeniería de sistemas", "Ingeniería de Sistemas"),
        ("negocios internacionales", "Negocios Internacionales"),
        ("adminsitracion", "Administración"),
        ("sitemas", "Ingeniería de Sistemas"),
        ("derehco", "Derecho"),
    ],
)
def test_specific_careers(classifier, message, career):
    intent, entities = classifier.classify(message)
    assert intent == "consulta_carrera_especifica"
    assert entities["career"] == career
    assert entities["classification_source"] == "rules"


def test_compound_career_and_admission(classifier):
    intent, entities = classifier.classify(
        "quiero informacion sobre administracion y admision"
    )
    assert intent == "consulta_carrera_especifica"
    assert entities["career"] == "Administración"
    assert entities["secondary_intents"] == ["consulta_admision"]
    assert entities["classification_source"] == "rules"


def test_explicit_stop_sets_stop_bot(classifier):
    intent, entities = classifier.classify("basta de mensajes")
    assert intent == "detener_conversacion"
    assert entities["stop_bot"] is True


def test_llm_is_only_used_as_fallback():
    class FakeLLM:
        def __init__(self):
            self.calls = []

        def classify(self, message):
            self.calls.append(message)
            return {"intent": "consulta_admision"}

    llm = FakeLLM()
    classifier = IntentClassifier(llm_service=llm)
    assert classifier.classify("hola")[0] == "saludo"
    assert llm.calls == []
    intent, entities = classifier.classify("quisiera conocer el proceso universitario")
    assert intent == "consulta_admision"
    assert entities["classification_source"] == "ollama"
    assert llm.calls == ["quisiera conocer el proceso universitario"]


def test_llm_cannot_stop_without_explicit_opt_out():
    class UnsafeLLM:
        def classify(self, message):
            return {
                "intent": "detener_conversacion",
                "response": "Listo, ya no responderé.",
                "stop_bot": True,
            }

    intent, entities = IntentClassifier(llm_service=UnsafeLLM()).classify("qué fue eso")
    assert intent == "no_entendido"
    assert entities["stop_bot"] is False
    assert "llm_response" not in entities
