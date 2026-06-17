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
        self._enrich_controlled_context(intent, entities)
        return intent, entities

    def _is_explicit_stop(self, text: str) -> bool:
        normalized = self.semantic_engine.normalize(text)
        return any(
            normalized == phrase or phrase in normalized
            for phrase in EXPLICIT_STOP_PHRASES
        )

    @staticmethod
    def _enrich_controlled_context(intent: str, entities: dict[str, Any]) -> None:
        institutional = {
            "consulta_proposito": "proposito",
            "consulta_mision": "mision",
            "consulta_vision": "vision",
            "consulta_valores": "valores",
            "consulta_ideario": "ideario",
            "consulta_modelo_educativo": "modelo_educativo",
            "consulta_onlife": "onlife",
            "consulta_modo_usil": "modo_usil",
            "consulta_competencias_sello": "competencias_sello",
            "consulta_aprendizaje_competencias": "aprendizaje_competencias",
            "consulta_perfil_egreso": "perfil_egreso",
            "consulta_pilares": "pilares",
            "consulta_sostenibilidad": "sostenibilidad",
            "consulta_laboratorios": "laboratorios",
        }
        modalities = {
            "consulta_modalidades_admision": None,
            "consulta_regular": "regular",
            "consulta_admision_destacada": "admision_destacada",
            "consulta_traslado_externo": "traslado_externo",
            "consulta_deportista_destacado": "deportista_destacado_alta_competencia",
            "consulta_bachillerato_internacional": "bachillerato_internacional",
            "consulta_becas_estado_pronabec": "becas_estado_pronabec",
            "consulta_documentos_modalidad": entities.get("modalidad"),
            "consulta_procedimiento_modalidad": entities.get("modalidad"),
            "consulta_beneficios_modalidad": entities.get("modalidad"),
            "consulta_convalidacion": entities.get("modalidad"),
        }
        if intent in institutional:
            entities.setdefault("tema", institutional[intent])
            entities.setdefault("source", "conocimiento_institucional")
        if intent in modalities:
            entities.setdefault("tema", "modalidades_admision")
            entities.setdefault("source", "conocimiento_institucional")
            if modalities[intent]:
                entities.setdefault("modalidad", modalities[intent])
