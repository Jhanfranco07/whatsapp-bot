import json
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.services.semantic_engine import SemanticEngine


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "conocimiento_institucional.json"
CAREERS_PATH = Path(__file__).resolve().parents[1] / "data" / "carreras.json"


class KnowledgeBase:
    """Busca respuestas verificadas que pueden ampliarse sin modificar Python."""

    def __init__(self, path: Path | None = None, careers_path: Path | None = None) -> None:
        self.path = path or DATA_PATH
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self.entries: list[dict[str, Any]] = data.get("entradas", [])
        self.careers_path = careers_path or CAREERS_PATH
        self.careers_data = self._read_careers()
        self._documents = [self._entry_document(entry) for entry in self._active_entries()]
        self._semantic_entries = self._active_entries()
        self._vectorizer = None
        self._vectors = None
        if self._documents:
            self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            self._vectors = self._vectorizer.fit_transform(self._documents)

    def find(
        self,
        message: str,
        intent: str | None = None,
        entities: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if intent:
            entry = self.find_by_intent(intent, entities)
            if entry:
                return entry
        normalized = SemanticEngine.normalize(message)
        message_tokens = set(normalized.split())
        best_entry = None
        best_score = 0.0
        for entry in self._active_entries():
            keywords = {SemanticEngine.normalize(keyword) for keyword in self._keywords(entry)}
            score = sum(
                1.0 if keyword in normalized else 0.0
                for keyword in keywords
                if keyword
            )
            token_keywords = {token for keyword in keywords for token in keyword.split()}
            if token_keywords:
                score += len(message_tokens & token_keywords) / len(token_keywords)
            if score > best_score:
                best_entry = entry
                best_score = score
        semantic_entry, semantic_score = self._semantic_match(normalized)
        if semantic_score >= best_score:
            best_entry = semantic_entry
            best_score = semantic_score
        return best_entry if best_score >= 0.32 else None

    def find_by_intent(
        self, intent: str, entities: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        entities = entities or {}
        modalidad = entities.get("modalidad")
        for entry in self._active_entries():
            if entry.get("intent") != intent:
                continue
            if modalidad and entry.get("modalidad_key") not in {None, modalidad, "general"}:
                continue
            return entry
        if intent in {
            "consulta_documentos_modalidad",
            "consulta_procedimiento_modalidad",
            "consulta_beneficios_modalidad",
            "consulta_convalidacion",
        }:
            return self.find_by_modalidad(modalidad)
        return None

    def find_by_modalidad(self, modalidad: str | None) -> dict[str, Any] | None:
        if not modalidad:
            return None
        for entry in self._active_entries():
            if entry.get("modalidad_key") == modalidad:
                return entry
        return None

    @classmethod
    def render(cls, entry: dict[str, Any]) -> str:
        response = str(
            entry.get("respuesta_corta") or entry.get("respuesta") or ""
        ).strip()
        source = str(entry.get("fuente_oficial") or entry.get("fuente_url") or "").strip()
        return f"{response}\n\nFuente oficial: {source}" if source else response

    @classmethod
    def add_entry(cls, entry: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
        target = path or DATA_PATH
        data = json.loads(target.read_text(encoding="utf-8-sig"))
        required = {"respuesta", "palabras_clave", "fuente_url"}
        missing = required - set(entry)
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(sorted(missing))}")
        entries = data.setdefault("entradas", [])
        item = {
            "id": entry.get("id") or f"contexto_{len(entries) + 1}",
            "tema": entry.get("tema", "general"),
            "palabras_clave": list(entry["palabras_clave"]),
            "respuesta": str(entry["respuesta"]).strip(),
            "fuente_url": str(entry["fuente_url"]).strip(),
            "verificado_el": entry.get("verificado_el"),
        }
        entries.append(item)
        target.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return item

    def _semantic_match(self, normalized_message: str) -> tuple[dict[str, Any] | None, float]:
        if self._vectorizer is None or self._vectors is None:
            return None, 0.0
        query = self._vectorizer.transform([normalized_message])
        similarities = cosine_similarity(query, self._vectors)[0]
        index = int(similarities.argmax())
        score = float(similarities[index])
        return self._semantic_entries[index], score

    @staticmethod
    def _entry_document(entry: dict[str, Any]) -> str:
        parts = [
            entry.get("tema", ""),
            entry.get("intent", ""),
            " ".join(KnowledgeBase._keywords(entry)),
            entry.get("respuesta", ""),
            entry.get("respuesta_corta", ""),
            entry.get("contenido", ""),
        ]
        return SemanticEngine.normalize(" ".join(parts))

    def _active_entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry.get("activo", True)]

    @staticmethod
    def _keywords(entry: dict[str, Any]) -> list[str]:
        return list(entry.get("palabras_clave") or entry.get("keywords") or [])

    def get_all_faculties(self) -> list[dict[str, Any]]:
        return list(self.careers_data.get("facultades", []))

    def get_all_careers(self) -> list[dict[str, Any]]:
        careers = self.careers_data.get("carreras")
        if careers:
            return list(careers)
        flat = []
        for faculty in self.get_all_faculties():
            for career in faculty.get("carreras", []):
                flat.append({**career, "facultad": faculty.get("nombre"), "facultad_slug": faculty.get("slug")})
        return flat

    def get_careers_by_faculty(self, faculty_slug_or_name: str) -> list[dict[str, Any]]:
        faculty = self.find_faculty(faculty_slug_or_name)
        return list(faculty.get("carreras", [])) if faculty else []

    def find_faculty(self, text: str) -> dict[str, Any] | None:
        normalized = SemanticEngine.normalize(text)
        best: tuple[int, dict[str, Any]] | None = None
        for faculty in self.get_all_faculties():
            aliases = [faculty.get("nombre", ""), faculty.get("slug", ""), *faculty.get("keywords", [])]
            for alias in aliases:
                normalized_alias = SemanticEngine.normalize(alias)
                if not normalized_alias:
                    continue
                if normalized == normalized_alias or normalized_alias in normalized:
                    score = len(normalized_alias)
                    if best is None or score > best[0]:
                        best = (score, faculty)
        return best[1] if best else None

    def find_career(self, text: str) -> dict[str, Any] | None:
        normalized = SemanticEngine.normalize(text)
        best: tuple[int, dict[str, Any]] | None = None
        for career in self.get_all_careers():
            aliases = [
                career.get("nombre", ""),
                career.get("slug", ""),
                *career.get("aliases", []),
                *career.get("keywords", []),
            ]
            for alias in aliases:
                normalized_alias = SemanticEngine.normalize(alias)
                if not normalized_alias:
                    continue
                if normalized == normalized_alias or normalized_alias in normalized:
                    score = len(normalized_alias)
                    if best is None or score > best[0]:
                        best = (score, career)
        return best[1] if best else None

    def get_career_detail(self, career_slug_or_name: str) -> dict[str, Any] | None:
        return self.find_career(career_slug_or_name)

    def get_faculty_of_career(self, career_slug_or_name: str) -> dict[str, Any] | None:
        career = self.find_career(career_slug_or_name)
        if not career:
            return None
        faculty_slug = career.get("facultad_slug")
        faculty_name = career.get("facultad")
        return self.find_faculty(faculty_slug or faculty_name or "")

    def get_related_careers(self, career_slug_or_name: str) -> list[dict[str, Any]]:
        career = self.find_career(career_slug_or_name)
        if not career:
            return []
        return [
            item
            for item in self.get_careers_by_faculty(career.get("facultad_slug") or "")
            if item.get("nombre") != career.get("nombre")
        ]

    def get_career_aliases(self) -> dict[str, str]:
        aliases = {}
        for career in self.get_all_careers():
            for alias in [career.get("nombre", ""), *career.get("aliases", [])]:
                if alias:
                    aliases[SemanticEngine.normalize(alias)] = career.get("nombre", "")
        return aliases

    def get_faculty_aliases(self) -> dict[str, str]:
        aliases = {}
        for faculty in self.get_all_faculties():
            for alias in [faculty.get("nombre", ""), faculty.get("slug", ""), *faculty.get("keywords", [])]:
                if alias:
                    aliases[SemanticEngine.normalize(alias)] = faculty.get("nombre", "")
        return aliases

    def _read_careers(self) -> dict[str, Any]:
        try:
            return json.loads(self.careers_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"facultades": [], "carreras": []}
