from typing import Any

from app.services.semantic_engine import EXPLICIT_STOP_PHRASES, SemanticEngine, get_semantic_engine


class IntentClassifier:
    """Adaptador compatible que delega la clasificación al motor semántico."""

    def __init__(self, semantic_engine: SemanticEngine | None = None) -> None:
        self.semantic_engine = semantic_engine or get_semantic_engine()

    def classify(
        self, original: str, conversation_context: dict[str, Any] | None = None
    ) -> tuple[str, dict[str, Any]]:
        result = self.semantic_engine.classify(original, conversation_context)
        intent = result.intent
        entities = {
            **result.entities,
            "confidence": result.confidence,
            "should_reply": result.should_reply,
            "classification_source": result.classifier,
        }

        if intent == "detener_conversacion" and not self._is_explicit_stop(original):
            intent = "fuera_de_alcance"
            entities["stop_bot"] = False
            entities["should_reply"] = False
        elif intent == "detener_conversacion":
            entities["stop_bot"] = True
        return intent, entities

    def _is_explicit_stop(self, text: str) -> bool:
        normalized = self.semantic_engine.normalize(text)
        return any(
            normalized == phrase or phrase in normalized
            for phrase in EXPLICIT_STOP_PHRASES
        )
