import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.knowledge_base import KnowledgeBase
from app.services.semantic_engine import SemanticEngine


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass
class ChatbotResult:
    bot_reply: str
    new_status: str
    opt_out: bool = False
    should_reply: bool = True


class ChatbotService:
    """Genera respuestas controladas exclusivamente desde datos y plantillas."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.replies: dict[str, list[str] | str] = json.loads(
            (DATA_DIR / "respuestas_base.json").read_text(encoding="utf-8")
        )
        self.careers: list[dict[str, Any]] = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8-sig")
        )["carreras"]
        self.institution: dict[str, Any] = json.loads(
            (DATA_DIR / "institucion.json").read_text(encoding="utf-8")
        )
        self.knowledge = KnowledgeBase()

    async def generate_response(
        self,
        intent: str,
        entities: dict[str, Any],
        contact_id: Any,
        user_message: str,
        conversation_context: dict[str, Any] | None = None,
        contact: Any = None,
    ) -> tuple[str | None, bool]:
        """Mantiene la interfaz asíncrona y devuelve una respuesta local."""
        verified = self.knowledge.find(user_message)
        result = self.respond(intent, entities, contact, conversation_context)
        if not result.should_reply or not entities.get("should_reply", True):
            return None, False
        if verified:
            return self._sanitize(self.knowledge.render(verified), user_message), True
        return self._sanitize(result.bot_reply, user_message), True

    def respond(
        self,
        intent: str,
        entities: dict[str, Any],
        contact: Any = None,
        context: dict[str, Any] | None = None,
    ) -> ChatbotResult:
        context = context or {}
        career = self._find_career(entities.get("carrera") or entities.get("career"))
        name = entities.get("name") or getattr(contact, "full_name", None)
        values = self._format_values(career, name)

        if intent == "ruido_conversacional":
            return ChatbotResult("", "RESPONDIO", should_reply=False)
        if intent in {"detener_conversacion", "salir_baja", "no_interesado"}:
            status = "NO_INTERESADO" if intent == "no_interesado" else "SALIR"
            return ChatbotResult(self._reply("baja", values), status, opt_out=True)
        if intent == "presentacion_nombre":
            return ChatbotResult(
                self._reply("presentacion_nombre", values), "RESPONDIO"
            )
        if intent == "agradecimiento" and context.get("last_career"):
            return ChatbotResult(
                f"De nada. Puedo seguir orientándote sobre {context['last_career']}.",
                "RESPONDIO",
            )
        if intent == "consulta_carrera_especifica" and not career:
            requested = entities.get("carrera") or entities.get("career")
            if requested in self.institution.get("carreras_oficiales", []):
                values["carrera"] = requested
                values["descripcion_carrera"] = (
                    "una carrera oficial de USIL. Su información específica puede "
                    "consultarse en el portal institucional."
                )

        key = self._reply_key(intent)
        reply = self._reply(key, values)
        if (
            intent == "consulta_carrera_especifica"
            and "consulta_admision" in entities.get("secondary_intents", [])
            and "admisión" not in reply.lower()
        ):
            reply = f"{reply}\n\nAdmisión: {values['link_admision']}"
        return ChatbotResult(reply, self._status_for(intent))

    def _format_values(
        self, career: dict[str, Any] | None, name: str | None
    ) -> dict[str, str]:
        institution = self.institution.get("institucion", {})
        campus = self.institution.get("campus", [])
        first_name = name.split()[0] if name else ""
        career_name = career["nombre"] if career else ""
        description = career.get("descripcion", career.get("descripcion_corta", "")) if career else ""
        field = career.get("campo_laboral", "") if career else ""
        return {
            "nombre": f", {first_name}" if first_name else "",
            "carrera": career_name,
            "descripcion_carrera": description,
            "campo_laboral": field or (
                f"El campo laboral de {career_name} puede abarcar distintas áreas "
                "relacionadas con su formación."
                if career_name else
                "El campo laboral depende de la carrera elegida."
            ),
            "portal_url": institution.get("portal_oficial", self.settings.portal_oficial_url),
            "link_admision": institution.get(
                "admision_pregrado",
                "https://descubre.usil.edu.pe/landings/pregrado/admision/",
            ),
            "campus_list": "\n".join(
                f"- {item['nombre']}: {item['direccion']}" for item in campus
            ),
            "campus_lista": "\n".join(
                f"- {item['nombre']}: {item['direccion']}" for item in campus
            ),
            "contacto_oficial": self._official_contact_text(),
        }

    def _official_contact_text(self) -> str:
        contact = self.institution.get("contacto", {})
        return (
            f"Admisión: {contact.get('central_admision', '')}\n"
            f"WhatsApp de Admisión: {contact.get('whatsapp_admision', '')}\n"
            f"Atención al Alumno: {contact.get('atencion_alumno', '')}\n"
            f"Correo: {contact.get('correo_atencion_alumno', '')}"
        ).strip()

    def _reply(self, key: str, values: dict[str, str]) -> str:
        variants = self.replies.get(key) or self.replies["no_entendido"]
        if isinstance(variants, str):
            variants = [variants]
        template = random.choice(variants)
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            fallback = self.replies["no_entendido"]
            fallback = fallback[0] if isinstance(fallback, list) else fallback
            return fallback.format(**values)

    @staticmethod
    def _reply_key(intent: str) -> str:
        mapping = {
            "consulta_carrera_especifica": "consulta_carrera_especifica",
            "consulta_campo_laboral": "consulta_campo_laboral",
            "comparacion_carrera": "comparacion_carrera",
            "consulta_duracion": "consulta_malla",
        }
        return mapping.get(intent, intent)

    @staticmethod
    def _status_for(intent: str) -> str:
        if intent in {
            "consulta_carreras",
            "consulta_carrera_especifica",
            "consulta_campo_laboral",
            "consulta_malla",
            "consulta_modalidad",
            "comparacion_carrera",
        }:
            return "INTERESADO_CARRERA"
        if intent == "consulta_admision":
            return "INTERESADO_ADMISION"
        if intent == "consulta_becas":
            return "INTERESADO_BECA"
        if intent == "consulta_portal":
            return "PIDIO_PORTAL"
        return "RESPONDIO"

    def _find_career(self, name: str | None) -> dict[str, Any] | None:
        if not name:
            return None
        target = SemanticEngine.normalize(name)
        for career in self.careers:
            aliases = [career["nombre"], *career.get("aliases", [])]
            if target in {SemanticEngine.normalize(alias) for alias in aliases}:
                return career
        return None

    @classmethod
    def _sanitize(cls, response: str, user_message: str) -> str:
        text = str(response).strip()
        if not cls._contains_emoji(user_message):
            text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) <= 800:
            return text
        shortened = text[:780].rstrip()
        boundary = max(shortened.rfind("."), shortened.rfind("?"), shortened.rfind("!"))
        return (shortened[: boundary + 1] if boundary >= 480 else shortened) + "..."

    @staticmethod
    def _contains_emoji(text: str) -> bool:
        return bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", str(text)))
