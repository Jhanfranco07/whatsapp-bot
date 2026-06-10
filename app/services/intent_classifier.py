import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from app.utils.text_utils import normalize_text, title_name


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class IntentClassifier:
    """Clasificador determinista basado exclusivamente en reglas y JSON."""

    def __init__(self, ai_service=None):
        # ai_service se conserva solo por compatibilidad con integraciones futuras.
        self.careers = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8")
        )["carreras"]

    def classify(self, original: str):
        text = normalize_text(original)
        name = self._extract_name(text)
        if name:
            return "presentacion_nombre", {"name": name}

        career = self._find_career(text)
        entities = {}
        if career:
            entities = {"career": career["nombre"], "area": career["area"]}

        if self._contains(text, [
            "no quiero mensajes", "ya no quiero mensajes", "ya no me escriban",
            "no estoy interesado", "no me interesa", "no gracias",
            "no deseo informacion", "salir", "baja", "cancelar",
        ]):
            return "salir_baja", entities
        if self._contains(text, [
            "que me llamen", "quiero una llamada", "pueden llamarme", "llamada telefonica",
            "llamen", "llamada",
        ]):
            return "quiere_llamada", entities
        if self._contains(text, [
            "hablar con asesor", "hablar con un asesor", "quiero hablar con alguien",
            "que me contacten", "quiero asesor", "asesor", "orientador",
            "orientacion personalizada", "comuniquense",
        ]):
            return "quiere_asesor", entities

        admission = self._contains(text, [
            "admision", "proceso de admision", "requisitos de admision", "como postulo",
            "postular", "inscripcion", "inscribirme", "examen de admision", "ingreso",
        ])
        if career:
            if admission:
                entities["secondary_intents"] = ["consulta_admision"]
            return "consulta_carrera_especifica", entities

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
