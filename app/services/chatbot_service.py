import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass
class ChatbotResult:
    bot_reply: str
    new_status: str
    requires_advisor: bool = False
    opt_out: bool = False
    advisor_request_needed: bool = False
    advisor_reason: str | None = None


class ChatbotService:
    def __init__(self):
        self.settings = get_settings()
        self.replies = json.loads(
            (DATA_DIR / "respuestas_base.json").read_text(encoding="utf-8")
        )
        self.careers = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8")
        )["carreras"]

    def respond(self, intent, entities, contact=None, context=None):
        context = context or {}
        portal = self.settings.portal_oficial_url
        name = entities.get("name") or getattr(contact, "full_name", None)
        first_name = name.split()[0] if name else None
        format_values = {
            "nombre": f", {first_name}" if first_name else "",
            "portal_url": portal,
        }

        if intent == "presentacion_nombre":
            presentation_values = {**format_values, "nombre": entities["name"]}
            return ChatbotResult(
                self._reply("presentacion_nombre", presentation_values, name), "RESPONDIO"
            )
        if intent in {"salir_baja", "no_interesado"}:
            status = "SALIR" if intent == "salir_baja" else "NO_INTERESADO"
            return ChatbotResult(self._reply("baja", format_values, name), status, opt_out=True)
        if intent == "quiere_asesor":
            career = context.get("last_career") or entities.get("career")
            reason = f"Interesado en {career}" if career else "Orientación"
            return ChatbotResult(
                self._reply("asesor", format_values, name),
                "QUIERE_ASESOR",
                True,
                advisor_request_needed=True,
                advisor_reason=reason,
            )
        if intent == "quiere_llamada":
            career = context.get("last_career") or entities.get("career")
            reason = f"Llamada sobre {career}" if career else "Llamada"
            return ChatbotResult(
                self._reply("llamada", format_values, name),
                "QUIERE_LLAMADA",
                True,
                advisor_request_needed=True,
                advisor_reason=reason,
            )
        if intent == "consulta_carrera_especifica":
            career = next(
                (item for item in self.careers if item["nombre"] == entities.get("career")),
                None,
            )
            if career:
                admission_note = (
                    " Para revisar también el proceso de admisión,"
                    if "consulta_admision" in entities.get("secondary_intents", [])
                    else " Para información oficial sobre malla, duración, modalidades o admisión,"
                )
                reply = (
                    f"¡Qué bueno que te interese {career['nombre']}! 😊\n"
                    f"{career['descripcion_corta']}\n\n"
                    f"{admission_note} revisa el portal de USIL:\n{career['url'] or portal}\n\n"
                    "También puedes pedir hablar con un asesor."
                )
                return ChatbotResult(reply, "INTERESADO_CARRERA")
        if intent == "consulta_carreras":
            return ChatbotResult(
                self._reply("consulta_carreras", format_values, name), "INTERESADO_CARRERA"
            )
        if intent == "consulta_admision":
            return ChatbotResult(
                self._reply("consulta_admision", format_values, name), "INTERESADO_ADMISION"
            )
        if intent == "consulta_becas":
            return ChatbotResult(
                self._reply("consulta_becas", format_values, name), "INTERESADO_BECA"
            )
        if intent == "consulta_portal":
            return ChatbotResult(
                self._reply("consulta_portal", format_values, name), "PIDIO_PORTAL"
            )
        if intent == "agradecimiento":
            last_career = context.get("last_career")
            if last_career:
                reply = (
                    f"¡De nada! 😊 Si deseas, también puedo registrar que un asesor "
                    f"te contacte para orientarte sobre {last_career}."
                )
                return ChatbotResult(reply, "RESPONDIO")
            return ChatbotResult(
                self._reply("agradecimiento", format_values, name), "RESPONDIO"
            )
        if intent == "saludo":
            return ChatbotResult(self._reply("saludo", format_values, name), "RESPONDIO")
        return ChatbotResult(
            self._reply("no_entendido", format_values, name), "RESPONDIO"
        )

    def _reply(self, key, values, seed=None):
        variants = self.replies[key]
        if isinstance(variants, str):
            variants = [variants]
        index = sum(ord(char) for char in str(seed or key)) % len(variants)
        return variants[index].format(**values)
