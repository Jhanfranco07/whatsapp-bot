import json
from pathlib import Path
from typing import Any

from app.services.semantic_engine import SemanticEngine


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "conocimiento_institucional.json"


class KnowledgeBase:
    """Busca respuestas verificadas que pueden ampliarse sin modificar Python."""

    def __init__(self, path: Path | None = None) -> None:
        data = json.loads((path or DATA_PATH).read_text(encoding="utf-8-sig"))
        self.entries: list[dict[str, Any]] = data.get("entradas", [])

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
        return best_entry if best_score >= 1.0 else None

    @staticmethod
    def render(entry: dict[str, Any]) -> str:
        response = str(entry["respuesta"]).strip()
        source = str(entry.get("fuente_url") or "").strip()
        return f"{response}\n\nFuente oficial: {source}" if source else response
