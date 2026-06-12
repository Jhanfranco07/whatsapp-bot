import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.llm import LLMService
from app.utils.text_utils import normalize_text


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass
class ChatbotResult:
    bot_reply: str
    new_status: str
    requires_advisor: bool = False
    opt_out: bool = False
    advisor_request_needed: bool = False
    advisor_reason: str | None = None
    should_reply: bool = True


class ChatbotService:
    def __init__(self, llm_service=None):
        self.settings = get_settings()
        self.llm_service = llm_service or LLMService()
        self.replies = json.loads(
            (DATA_DIR / "respuestas_base.json").read_text(encoding="utf-8")
        )
        self.careers = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8")
        )["carreras"]
        self.institution = json.loads(
            (DATA_DIR / "institucion.json").read_text(encoding="utf-8")
        )

    async def generate_response(
        self,
        intent: str,
        entities: dict,
        contact_id,
        user_message: str,
        conversation_context: dict | None = None,
        contact=None,
    ) -> tuple[str | None, bool]:
        """Usa Ollama como redactor final y conserva plantillas como fallback."""
        context = conversation_context or {}
        fallback_entities = {
            key: value for key, value in entities.items() if key != "llm_response"
        }
        fallback = self.respond(intent, fallback_entities, contact, context)
        should_reply = fallback.should_reply and entities.get("should_reply", True)
        if not should_reply:
            return None, False

        fixed_intents = {
            "detener_conversacion",
            "salir_baja",
            "no_interesado",
            "ruido_conversacional",
            "saludo",
        }
        if intent in fixed_intents:
            return fallback.bot_reply, True

        relevant_history = self._select_relevant_history(
            user_message, intent, entities, context
        )
        career_name = entities.get("career") or entities.get("carrera")
        if not career_name and relevant_history:
            career_name = context.get("last_career")
        career_info = self._find_career_info(career_name)
        llm_context = {
            "institucion": self.institution,
            "carrera_info": career_info,
            "historial": relevant_history,
            "plantilla_guia": fallback.bot_reply,
            "intent_actual": intent,
        }
        generated = await self.llm_service.generate_response(
            user_message=user_message,
            intent=intent,
            context=llm_context,
        )
        if generated.get("response"):
            return generated["response"], bool(generated.get("should_reply", True))
        return fallback.bot_reply, True

    def respond(self, intent, entities, contact=None, context=None):
        context = context or {}
        portal = self.settings.portal_oficial_url
        name = entities.get("name") or getattr(contact, "full_name", None)
        first_name = name.split()[0] if name else None
        format_values = {
            "nombre": f", {first_name}" if first_name else "",
            "portal_url": portal,
        }
        if entities.get("llm_response") and intent in {
            "consulta_carrera_especifica",
            "consulta_campo_laboral",
            "comparacion_carrera",
            "consulta_modalidad",
            "consulta_institucional",
            "fuera_de_alcance",
            "no_entendido",
        }:
            status = (
                "INTERESADO_CARRERA"
                if intent in {
                    "consulta_carrera_especifica",
                    "consulta_campo_laboral",
                    "comparacion_carrera",
                    "consulta_modalidad",
                }
                else "RESPONDIO"
            )
            return ChatbotResult(
                self._with_orientation_closing(entities["llm_response"], format_values),
                status,
                should_reply=entities.get("should_reply", True),
            )

        if intent == "presentacion_nombre":
            presentation_values = {**format_values, "nombre": entities["name"]}
            return ChatbotResult(
                self._reply("presentacion_nombre", presentation_values, name), "RESPONDIO"
            )
        if intent == "ruido_conversacional":
            return ChatbotResult("", "RESPONDIO", should_reply=False)
        if intent in {"detener_conversacion", "salir_baja", "no_interesado"}:
            status = "NO_INTERESADO" if intent == "no_interesado" else "SALIR"
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
                )
                return ChatbotResult(reply, "INTERESADO_CARRERA")
            if entities.get("career") in self.institution["carreras_oficiales"]:
                reply = (
                    f"¡Qué bueno que te interese {entities['career']}! 😊 "
                    "Para información oficial sobre malla, duración, modalidades "
                    f"y admisión, revisa el portal de USIL: {portal}."
                )
                return ChatbotResult(reply, "INTERESADO_CARRERA")
        if intent == "consulta_carreras":
            return ChatbotResult(
                self._reply("consulta_carreras", format_values, name), "INTERESADO_CARRERA"
            )
        if intent == "consulta_campo_laboral":
            return ChatbotResult(
                self._reply("consulta_campo_laboral", format_values, name),
                "INTERESADO_CARRERA",
            )
        if intent in {
            "comparacion_carrera",
            "consulta_malla",
            "consulta_duracion",
            "consulta_modalidad",
        }:
            reply_key = {
                "comparacion_carrera": "comparacion_carrera",
                "consulta_malla": "consulta_malla",
                "consulta_duracion": "consulta_duracion",
                "consulta_modalidad": "consulta_modalidad",
            }[intent]
            return ChatbotResult(
                self._reply(reply_key, format_values, name), "INTERESADO_CARRERA"
            )
        if intent == "consulta_admision":
            return ChatbotResult(
                self._reply("consulta_admision", format_values, name), "INTERESADO_ADMISION"
            )
        if intent == "consulta_costos":
            return ChatbotResult(
                self._reply("consulta_costos", format_values, name), "RESPONDIO"
            )
        if intent == "consulta_campus":
            campus_lines = "\n".join(
                f"- {item['nombre']}: {item['direccion']}"
                for item in self.institution["campus"]
            )
            return ChatbotResult(
                self._reply(
                    "consulta_campus",
                    {**format_values, "campus_list": campus_lines},
                    name,
                ),
                "RESPONDIO",
            )
        if intent == "consulta_internacionalidad":
            return ChatbotResult(
                self._reply("consulta_internacionalidad", format_values, name),
                "RESPONDIO",
            )
        if intent == "consulta_institucional":
            return ChatbotResult(
                self._reply("consulta_institucional", format_values, name), "RESPONDIO"
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
        if intent == "despedida":
            return ChatbotResult(self._reply("despedida", format_values, name), "RESPONDIO")
        if intent == "fuera_de_alcance":
            return ChatbotResult(
                self._reply("fuera_de_alcance", format_values, name), "RESPONDIO"
            )
        return ChatbotResult(
            self._reply("no_entendido", format_values, name), "RESPONDIO"
        )

    def _reply(self, key, values, seed=None):
        variants = self.replies[key]
        if isinstance(variants, str):
            variants = [variants]
        return random.choice(variants).format(**values)

    def _with_orientation_closing(self, response, values):
        response = str(response).strip()
        if "usil.edu.pe" in response:
            return response
        closing = random.choice(self.replies["cierres_orientacion"]).format(**values)
        return f"{response}\n\n{closing}"

    def _find_career_info(self, career_name):
        if not career_name:
            return None
        target = normalize_text(career_name)
        for career in self.careers:
            aliases = [career["nombre"], *career.get("aliases", [])]
            if target in {normalize_text(value) for value in aliases}:
                return career
        return None

    @staticmethod
    def _select_relevant_history(user_message, intent, entities, context):
        history = list(context.get("historial", []))[-3:]
        if not history:
            return []
        text = normalize_text(user_message)
        is_followup = bool(
            re.match(
                r"^(y|entonces|tambien|esa|ese|eso|esto|ademas|pero|"
                r"cuanto|donde|como|por que|de que|en que|que|y en)",
                text,
            )
        )
        current_career = entities.get("career") or entities.get("carrera")
        same_career = bool(
            current_career
            and normalize_text(current_career) == normalize_text(context.get("last_career"))
        )
        same_intent = intent == context.get("last_intent")
        return history if is_followup or (same_career and same_intent) else []
