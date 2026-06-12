import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path

from app.llm import LLMService
from app.llm.provider import LLMError
from app.utils.text_utils import normalize_text, title_name


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
logger = logging.getLogger(__name__)


class IntentClassifier:
    """Clasificador determinista basado exclusivamente en reglas y JSON."""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service or LLMService()
        self.careers = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8")
        )["carreras"]

    def classify(self, original: str):
        intent, entities = self._classify_rules(original)
        requires_llm_response = entities.pop("requires_llm_response", False)
        if intent != "no_entendido" and not requires_llm_response:
            return intent, {**entities, "classification_source": "rules"}
        try:
            llm_result = self.llm_service.classify(original)
        except LLMError as error:
            logger.warning("Clasificación LLM no disponible: %s", error)
            llm_result = None
        if llm_result:
            llm_entities = llm_result.get("entities", {})
            llm_intent = llm_result["intent"]
            explicit_stop = self._is_explicit_stop(normalize_text(original))
            llm_response = llm_result.get("response")
            if llm_intent == "detener_conversacion" and not explicit_stop:
                logger.warning(
                    "Se ignoró una baja no explícita propuesta por Ollama: %r",
                    original,
                )
                llm_intent = "no_entendido"
                llm_response = None
            if requires_llm_response and llm_intent == "no_entendido":
                llm_intent = intent
            merged_entities = {
                **entities,
                "career": llm_entities.get("carrera") or entities.get("career"),
                "topic": llm_entities.get("tema"),
                "confidence": llm_result.get("confidence", 0.0),
                "response_key": llm_result.get("response_key", "fallback"),
                "llm_response": llm_response,
                "should_reply": llm_result.get("should_reply", True),
                "should_escalate": llm_result.get("should_escalate", False),
                "stop_bot": explicit_stop and llm_intent == "detener_conversacion",
            }
            merged_entities = {
                key: value for key, value in merged_entities.items() if value is not None
            }
            return llm_intent, {**merged_entities, "classification_source": "ollama"}
        if requires_llm_response:
            return intent, {**entities, "classification_source": "rules"}
        return "no_entendido", {"classification_source": "rules"}

    def _classify_rules(self, original: str):
        text = normalize_text(original)
        name = self._extract_name(text)
        if name:
            return "presentacion_nombre", {"name": name}

        career = self._find_career(text)
        entities = {}
        if career:
            entities = {"career": career["nombre"], "area": career["area"]}

        if self._is_explicit_stop(text):
            return "detener_conversacion", {**entities, "stop_bot": True}
        if self._is_conversational_noise(text):
            return "ruido_conversacional", {"should_reply": False}
        if self._contains(text, [
            "que me llamen", "quiero una llamada", "pueden llamarme", "llamada telefonica",
            "llamen", "llamada",
        ]):
            return "quiere_llamada", entities
        if self._contains(text, [
            "hablar con asesor", "hablar con un asesor", "quiero hablar con alguien",
            "hablar con una persona", "hablar con jhan", "que me contacten",
            "quiero asesor", "asesor", "orientador", "contacto",
            "orientacion personalizada", "comuniquense",
        ]):
            return "quiere_asesor", entities
        if self._contains(text, ["zonificar"]):
            return "fuera_de_alcance", {**entities, "should_reply": False}

        admission = self._contains(text, [
            "admision", "proceso de admision", "requisitos de admision", "como postulo",
            "postular", "inscripcion", "inscribirme", "examen de admision", "ingreso",
        ])
        if self._contains(text, [
            "en que trabaja", "campo laboral", "salidas laborales",
            "donde puedo trabajar", "en donde trabaja",
        ]):
            return "consulta_campo_laboral", {
                **entities,
                "requires_llm_response": True,
            }
        if self._contains(text, [
            "campus", "sede", "sedes", "ubicacion", "donde queda",
            "la molina", "lima norte", "magdalena",
        ]):
            return "consulta_campus", entities
        if self._contains(text, [
            "internacionalidad", "intercambio", "intercambios", "doble grado",
            "convenios internacionales", "study abroad", "study tour", "disney international",
        ]):
            return "consulta_internacionalidad", entities
        specialized_rules = [
            ("comparacion_carrera", ["se asemeja", "comparar", "comparacion", "parecida", "se parece", "similar"]),
            ("consulta_malla", ["malla", "malla curricular", "cursos", "plan de estudios"]),
            ("consulta_duracion", ["duracion", "cuanto dura", "años dura", "ciclos dura"]),
            ("consulta_modalidad", ["modalidad", "presencial", "virtual", "semipresencial"]),
            ("consulta_costos", ["costo", "costos", "precio", "pension", "mensualidad"]),
        ]
        for intent, phrases in specialized_rules:
            if self._contains(text, phrases):
                return intent, {
                    **entities,
                    "requires_llm_response": intent in {
                        "comparacion_carrera",
                        "consulta_modalidad",
                    },
                }
        if career:
            if admission:
                entities["secondary_intents"] = ["consulta_admision"]
            if self._contains(text, ["que es", "de que trata", "que se ve", "como es"]):
                entities["requires_llm_response"] = True
            return "consulta_carrera_especifica", entities

        if self._contains(text, [
            "que es usil", "sobre usil", "informacion de usil",
            "informacion institucional", "universidad usil",
        ]):
            return "consulta_institucional", {"requires_llm_response": True}

        rules = [
            ("consulta_becas", [
                "beca", "becas", "descuento", "descuentos", "beneficios",
                "apoyo economico", "media beca", "pension",
            ]),
            ("consulta_admision", [
                "admision", "proceso de admision", "requisitos de admision", "como postulo",
                "postular", "inscripcion", "inscribirme", "examen de admision", "ingreso",
            ]),
            ("consulta_portal", [
                "mandame el link", "pasame el link", "pagina oficial", "link", "enlace",
                "pagina", "portal", "web", "informacion oficial",
            ]),
            ("consulta_carreras", [
                "que carreras tienen", "quiero saber carreras", "opciones de carrera",
                "quiero estudiar", "que puedo estudiar", "areas de estudio", "carreras", "carrera",
            ]),
            ("agradecimiento", [
                "gracias por la informacion", "muchas gracias", "listo gracias",
                "ok gracias", "gracias",
            ]),
            ("despedida", ["adios", "hasta luego", "nos vemos", "chau"]),
            ("saludo", [
                "buenos dias", "buenas tardes", "buenas noches", "que tal", "hola", "buenas",
            ]),
        ]
        for intent, phrases in rules:
            if self._contains(text, phrases):
                return intent, {}
        return "no_entendido", {}

    def _find_career(self, text):
        matches = []
        for career in self.careers:
            aliases = [career["nombre"], *career["aliases"]]
            for alias in aliases:
                normalized = normalize_text(alias)
                if normalized and re.search(rf"\b{re.escape(normalized)}\b", text):
                    matches.append((len(normalized), career))
        return max(matches, default=(0, None), key=lambda item: item[0])[1]

    @staticmethod
    def _extract_name(text):
        patterns = [
            r"^(?:hola\s+)?me llamo\s+(.+)$",
            r"^(?:hola\s+)?mi nombre es\s+(.+)$",
            r"^(?:hola\s+)?soy\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                candidate = match.group(1).strip()
                if 1 <= len(candidate.split()) <= 4 and not any(
                    word in candidate
                    for word in ("estudiante", "interesado", "interesada", "asesor")
                ):
                    return title_name(candidate)
        return None

    @staticmethod
    def _contains(text, phrases):
        tokens = text.split()
        for phrase in phrases:
            normalized = normalize_text(phrase)
            if re.search(rf"\b{re.escape(normalized)}\b", text):
                return True
            if " " not in normalized and len(normalized) >= 5:
                if any(
                    len(token) >= 5
                    and SequenceMatcher(None, token, normalized).ratio() >= 0.84
                    for token in tokens
                ):
                    return True
        return False

    @staticmethod
    def _is_explicit_stop(text):
        exact_commands = {
            "basta",
            "salir",
            "baja",
            "cancelar",
            "detente",
            "stop",
        }
        if text in exact_commands:
            return True
        explicit_phrases = [
            "no quiero mensajes",
            "ya no quiero mensajes",
            "ya no me escriban",
            "no me escriban mas",
            "dejen de escribirme",
            "deja de escribirme",
            "dejar de recibir mensajes",
            "no deseo recibir mensajes",
            "no deseo informacion",
            "no quiero informacion",
            "darme de baja",
            "quiero darme de baja",
            "basta de mensajes",
        ]
        return any(
            re.search(rf"\b{re.escape(phrase)}\b", text)
            for phrase in explicit_phrases
        )

    @staticmethod
    def _is_conversational_noise(text):
        if text in {"xd", "ok", "okay", "ya", "aja", "ah", "mmm", "jiji", "jeje"}:
            return True
        compact = re.sub(r"\s+", "", text)
        return bool(re.fullmatch(r"(?:ja){2,}|j+a+j+a+|(?:je){2,}|(?:ji){2,}", compact))
