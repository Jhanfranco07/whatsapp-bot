import json
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.services.semantic_engine import SemanticEngine


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "conocimiento_institucional.json"


class KnowledgeBase:
    """Busca respuestas verificadas que pueden ampliarse sin modificar Python."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_PATH
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self.entries: list[dict[str, Any]] = data.get("entradas", [])
        self._documents = [self._entry_document(entry) for entry in self.entries]
        self._vectorizer = None
        self._vectors = None
        if self._documents:
            self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            self._vectors = self._vectorizer.fit_transform(self._documents)

    def find(self, message: str) -> dict[str, Any] | None:
        normalized = SemanticEngine.normalize(message)
        message_tokens = set(normalized.split())
        best_entry = None
        best_score = 0.0
        for entry in self.entries:
            keywords = {
                SemanticEngine.normalize(keyword)
                for keyword in entry.get("palabras_clave", [])
            }
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

    @staticmethod
    def render(entry: dict[str, Any]) -> str:
        response = str(entry["respuesta"]).strip()
        source = str(entry.get("fuente_url") or "").strip()
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
        return self.entries[index], score

    @staticmethod
    def _entry_document(entry: dict[str, Any]) -> str:
        parts = [
            entry.get("tema", ""),
            " ".join(entry.get("palabras_clave", [])),
            entry.get("respuesta", ""),
        ]
        return SemanticEngine.normalize(" ".join(parts))
