import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


DATA_DIR = Path(__file__).resolve().parents[1] / "data"

EXPLICIT_STOP_PHRASES = (
    "basta",
    "stop",
    "detente",
    "ya no me escriban",
    "no quiero mensajes",
    "quiero darme de baja",
)


@dataclass(frozen=True)
class ClassificationResult:
    """Resultado normalizado producido por el motor semántico."""

    intent: str
    confidence: float
    entities: dict[str, Any]
    should_reply: bool
    classifier: str


class SemanticEngine:
    """Clasificador en cascada con reglas, alias, TF-IDF y Levenshtein."""

    def __init__(
        self,
        careers_path: Path | None = None,
        corpus_path: Path | None = None,
    ) -> None:
        careers_path = careers_path or DATA_DIR / "carreras.json"
        corpus_path = corpus_path or DATA_DIR / "intent_corpus.json"
        self.careers: list[dict[str, Any]] = json.loads(
            careers_path.read_text(encoding="utf-8-sig")
        )["carreras"]
        self.corpus: dict[str, list[str]] = json.loads(
            corpus_path.read_text(encoding="utf-8-sig")
        )
        self.corpus_phrases: list[str] = []
        self.corpus_intents: list[str] = []
        for intent, phrases in self.corpus.items():
            for phrase in phrases:
                self.corpus_phrases.append(self.normalize(phrase))
                self.corpus_intents.append(intent)
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.corpus_vectors = self.vectorizer.fit_transform(self.corpus_phrases)

    @property
    def intents_loaded(self) -> int:
        return len(self.corpus)

    def classify(
        self, text: str, conversation_context: dict[str, Any] | None = None
    ) -> ClassificationResult:
        """Clasifica texto siguiendo el pipeline semántico en cascada."""
        normalized = self.normalize(text)
        exact = self._classify_exact(normalized)
        if exact:
            return exact

        careers = self._find_careers(normalized)
        topic = self._detect_topic(normalized)
        if careers:
            intent = (
                "consulta_carrera_especifica"
                if topic == "consulta_admision"
                else topic or "consulta_carrera_especifica"
            )
            entities: dict[str, Any] = {
                "carrera": careers[0]["nombre"],
                "career": careers[0]["nombre"],
                "area": careers[0].get("area"),
            }
            if len(careers) > 1:
                entities["carreras"] = [item["nombre"] for item in careers]
            if topic:
                entities["tema"] = topic.removeprefix("consulta_")
            if topic == "consulta_admision":
                entities["secondary_intents"] = ["consulta_admision"]
            return ClassificationResult(intent, 0.98, entities, True, "rules")

        topic_rule = self._classify_topic_rule(normalized)
        if topic_rule:
            return topic_rule
        return self._classify_tfidf(normalized)

    @staticmethod
    def normalize(text: str) -> str:
        """Normaliza texto conservando solamente interrogación y exclamación."""
        value = unicodedata.normalize("NFKD", str(text or "").lower())
        value = "".join(char for char in value if not unicodedata.combining(char))
        value = re.sub(r"[^\w\s¿?¡!]", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    def is_explicit_stop(self, text: str) -> bool:
        normalized = self.normalize(text)
        return any(
            normalized == phrase
            or re.search(rf"\b{re.escape(phrase)}\b", normalized)
            for phrase in EXPLICIT_STOP_PHRASES
        )

    def _classify_exact(self, text: str) -> ClassificationResult | None:
        name = self._extract_name(text)
        if name:
            return ClassificationResult(
                "presentacion_nombre", 1.0, {"name": name}, True, "rules"
            )
        if self.is_explicit_stop(text):
            return ClassificationResult(
                "detener_conversacion",
                1.0,
                {"stop_bot": True},
                True,
                "rules",
            )
        if self._is_noise(text):
            return ClassificationResult(
                "ruido_conversacional", 1.0, {}, False, "rules"
            )
        if text in {
            "hola",
            "buenos dias",
            "buenas tardes",
            "buenas noches",
            "hi",
            "hey",
            "buen dia",
        }:
            return ClassificationResult("saludo", 1.0, {}, True, "rules")
        if text in {
            "gracias",
            "muchas gracias",
            "ok gracias",
            "genial gracias",
            "no gracias",
        }:
            return ClassificationResult("agradecimiento", 1.0, {}, True, "rules")
        return None

    @staticmethod
    def _extract_name(text: str) -> str | None:
        for pattern in (
            r"^(?:hola\s+)?me llamo\s+(.+)$",
            r"^(?:hola\s+)?mi nombre es\s+(.+)$",
            r"^(?:hola\s+)?soy\s+(.+)$",
        ):
            match = re.match(pattern, text)
            if match and 1 <= len(match.group(1).split()) <= 4:
                return " ".join(word.capitalize() for word in match.group(1).split())
        return None

    @staticmethod
    def _is_noise(text: str) -> bool:
        if text in {"xd", "ok", "ya", "aja", "jeje", "jiji", "😂", "😂😂"}:
            return True
        compact = re.sub(r"\s+", "", text)
        return bool(re.fullmatch(r"(?:ja){2,}|j+a+j+a+|(?:je){2,}|(?:ji){2,}", compact))

    def _find_careers(self, text: str) -> list[dict[str, Any]]:
        matches: list[tuple[int, dict[str, Any]]] = []
        for career in self.careers:
            aliases = [career["nombre"], *career.get("aliases", [])]
            for alias in aliases:
                normalized_alias = self.normalize(alias)
                if normalized_alias and re.search(
                    rf"\b{re.escape(normalized_alias)}\b", text
                ):
                    matches.append((len(normalized_alias), career))
                    break
        matches.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in matches]

    @staticmethod
    def _detect_topic(text: str) -> str | None:
        topics = [
            ("comparacion_carrera", ("diferencia", "comparar", "comparacion", "versus", " vs ", "similar")),
            ("consulta_campo_laboral", ("campo laboral", "en que trabaja", "salidas laborales", "donde trabaja")),
            ("consulta_costos", ("costo", "costos", "precio", "pension", "mensualidad", "cuanto cuesta")),
            ("consulta_admision", ("admision", "postular", "inscripcion", "ingreso")),
            ("consulta_campus", ("campus", "sede", "ubicacion", "donde queda", "direccion")),
            ("consulta_malla", ("malla", "cursos", "plan de estudios", "ciclos", "duracion", "cuanto dura")),
            ("consulta_modalidad", ("modalidad", "virtual", "presencial", "semipresencial", "online")),
        ]
        padded = f" {text} "
        for intent, phrases in topics:
            if any(phrase in padded for phrase in phrases):
                return intent
        return None

    def _classify_topic_rule(self, text: str) -> ClassificationResult | None:
        direct_rules = [
            ("consulta_contacto", ("asesor", "orientador", "hablar con una persona", "que me contacten")),
            ("consulta_contacto", ("llamada", "que me llamen", "pueden llamarme", "contacto oficial")),
            ("consulta_internacionalidad", ("intercambio", "doble grado", "internacionalidad", "study abroad")),
            ("consulta_becas", ("beca", "becas", "descuento", "beneficios")),
            ("consulta_portal", ("portal", "pagina oficial", "link", "enlace")),
            ("consulta_institucional", ("que es usil", "sobre usil", "universidad usil")),
            ("consulta_carreras", ("que carreras", "lista de carreras", "carreras", "que puedo estudiar")),
            ("despedida", ("adios", "hasta luego", "nos vemos", "chau")),
            ("fuera_de_alcance", ("zonificar",)),
        ]
        padded = f" {text} "
        for intent, phrases in direct_rules:
            if any(phrase in padded for phrase in phrases):
                return ClassificationResult(
                    intent,
                    0.95,
                    {},
                    intent != "fuera_de_alcance",
                    "rules",
                )
        topic = self._detect_topic(text)
        if topic:
            return ClassificationResult(topic, 0.9, {}, True, "rules")
        return None

    def _classify_tfidf(self, text: str) -> ClassificationResult:
        query_vector = self.vectorizer.transform([text])
        similarities = cosine_similarity(query_vector, self.corpus_vectors)[0]
        best_index = int(similarities.argmax())
        best_score = float(similarities[best_index])
        if best_score < 0.25:
            return ClassificationResult(
                "fuera_de_alcance", best_score, {}, False, "tfidf"
            )
        if best_score <= 0.40:
            return self._classify_levenshtein(text, similarities)
        return ClassificationResult(
            self.corpus_intents[best_index],
            best_score,
            {},
            self.corpus_intents[best_index] != "fuera_de_alcance",
            "tfidf",
        )

    def _classify_levenshtein(
        self, text: str, similarities: Any
    ) -> ClassificationResult:
        best_index = 0
        best_score = -1.0
        for index, phrase in enumerate(self.corpus_phrases):
            max_length = max(len(text), len(phrase), 1)
            levenshtein_norm = Levenshtein.distance(text, phrase) / max_length
            score = 0.7 * float(similarities[index]) + 0.3 * (1 - levenshtein_norm)
            if score > best_score:
                best_score = score
                best_index = index
        intent = self.corpus_intents[best_index]
        return ClassificationResult(
            intent,
            max(0.0, min(1.0, best_score)),
            {},
            intent != "fuera_de_alcance",
            "levenshtein_blend",
        )


_semantic_engine: SemanticEngine | None = None
_semantic_engine_lock = Lock()


def get_semantic_engine() -> SemanticEngine:
    """Devuelve el singleton inicializado del motor semántico."""
    global _semantic_engine
    if _semantic_engine is None:
        with _semantic_engine_lock:
            if _semantic_engine is None:
                _semantic_engine = SemanticEngine()
    return _semantic_engine
