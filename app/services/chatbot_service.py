import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.contact_states import ContactState
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

    CONTROLLED_KNOWLEDGE_INTENTS = {
        "consulta_proposito",
        "consulta_mision",
        "consulta_vision",
        "consulta_valores",
        "consulta_ideario",
        "consulta_modelo_educativo",
        "consulta_onlife",
        "consulta_modo_usil",
        "consulta_competencias_sello",
        "consulta_aprendizaje_competencias",
        "consulta_perfil_egreso",
        "consulta_pilares",
        "consulta_sostenibilidad",
        "consulta_laboratorios",
        "consulta_modalidades_admision",
        "consulta_regular",
        "consulta_admision_destacada",
        "consulta_traslado_externo",
        "consulta_deportista_destacado",
        "consulta_bachillerato_internacional",
        "consulta_becas_estado_pronabec",
        "consulta_documentos_modalidad",
        "consulta_procedimiento_modalidad",
        "consulta_beneficios_modalidad",
        "consulta_convalidacion",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.replies: dict[str, list[str] | str] = json.loads(
            (DATA_DIR / "respuestas_base.json").read_text(encoding="utf-8")
        )
        self.careers: list[dict[str, Any]] = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8-sig")
        )["carreras"]
        self.faculties: list[dict[str, Any]] = json.loads(
            (DATA_DIR / "carreras.json").read_text(encoding="utf-8-sig")
        ).get("facultades", [])
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
        result = self.respond(intent, entities, contact, conversation_context)
        if not result.should_reply or not entities.get("should_reply", True):
            return None, False
        verified = self.knowledge.find(user_message, intent=intent, entities=entities)
        if verified:
            reply = self._render_verified_response(intent, verified, user_message)
            return self._sanitize(reply, user_message), True
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
            return ChatbotResult("", ContactState.RESPONDIO, should_reply=False)
        if intent in {"detener_conversacion", "salir_baja", "no_interesado"}:
            status = ContactState.NO_INTERESADO if intent == "no_interesado" else ContactState.SALIR
            return ChatbotResult(self._reply("baja", values), status, opt_out=True)
        if intent == "presentacion_nombre":
            return ChatbotResult(
                self._reply("presentacion_nombre", values), ContactState.RESPONDIO
            )
        if intent == "agradecimiento" and context.get("last_career"):
            return ChatbotResult(
                f"De nada. Puedo seguir orientándote sobre {context['last_career']}.",
                ContactState.RESPONDIO,
            )
        career_response = self._career_response(intent, entities)
        if career_response:
            return ChatbotResult(career_response, self._status_for(intent))
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
            return ContactState.INTERESADO_CARRERA
        if intent == "consulta_admision":
            return ContactState.INTERESADO_ADMISION
        if intent == "consulta_becas":
            return ContactState.INTERESADO_BECA
        if intent == "consulta_portal":
            return ContactState.PIDIO_PORTAL
        if intent == "consulta_contacto":
            return ContactState.PIDIO_CONTACTO
        if intent in ChatbotService.CONTROLLED_KNOWLEDGE_INTENTS:
            admission_intents = {
                "consulta_modalidades_admision",
                "consulta_regular",
                "consulta_admision_destacada",
                "consulta_traslado_externo",
                "consulta_deportista_destacado",
                "consulta_bachillerato_internacional",
                "consulta_becas_estado_pronabec",
                "consulta_documentos_modalidad",
                "consulta_procedimiento_modalidad",
                "consulta_beneficios_modalidad",
                "consulta_convalidacion",
            }
            return (
                ContactState.INTERESADO_ADMISION
                if intent in admission_intents
                else ContactState.RESPONDIO
            )
        return ContactState.RESPONDIO

    def _render_verified_response(
        self, intent: str, entry: dict[str, Any], user_message: str
    ) -> str:
        title = str(entry.get("titulo") or "esta modalidad").strip()
        if intent == "consulta_documentos_modalidad":
            body = self._bullet_list(entry.get("documentos")) or str(entry.get("respuesta_corta", ""))
            reply = f"Documentos principales para {title}:\n{body}"
        elif intent == "consulta_procedimiento_modalidad":
            body = self._bullet_list(entry.get("procedimiento")) or str(entry.get("respuesta_corta", ""))
            reply = f"Procedimiento para {title}:\n{body}"
        elif intent == "consulta_beneficios_modalidad":
            body = self._bullet_list(entry.get("beneficios")) or str(entry.get("respuesta_corta", ""))
            reply = f"Beneficios de {title}:\n{body}"
        elif intent == "consulta_convalidacion":
            reply = f"Sobre convalidación: {entry.get('convalidacion') or entry.get('respuesta_corta', '')}"
            if "según evaluación" not in reply.lower():
                reply = f"{reply} La convalidación se confirma según evaluación."
        else:
            reply = str(entry.get("respuesta_corta") or entry.get("respuesta") or "").strip()
        closure = self._controlled_closure(entry)
        if closure and closure not in reply:
            reply = f"{reply}\n\n{closure}"
        return reply

    def _controlled_closure(self, entry: dict[str, Any]) -> str:
        key = (
            "cierres_admision"
            if entry.get("modalidad_key") or str(entry.get("intent", "")).startswith("consulta_") and "admision" in str(entry.get("intent", ""))
            else "cierres_institucionales"
        )
        variants = self.replies.get(key) or []
        return random.choice(variants) if variants else ""

    @staticmethod
    def _bullet_list(items: Any) -> str:
        if isinstance(items, list):
            return "\n".join(f"- {str(item).strip()}" for item in items if str(item).strip())
        return str(items or "").strip()

    def _career_response(self, intent: str, entities: dict[str, Any]) -> str | None:
        if intent == "consulta_facultades":
            names = [faculty["nombre"].removeprefix("Facultad de ") for faculty in self.faculties]
            return self._with_career_closure(
                f"USIL cuenta con facultades como {self._join_items(names)}."
            )
        if intent == "consulta_carreras":
            return self._with_career_closure(
                "USIL ofrece carreras en áreas como negocios, ingeniería, salud, derecho, "
                "educación, comunicación, arquitectura, artes, hotelería, turismo y "
                "gastronomía. Si deseas, puedes preguntarme por una facultad específica, "
                "por ejemplo: carreras de Ingeniería o carreras de Ciencias Empresariales."
            )
        if intent == "consulta_carreras_por_facultad":
            faculty = self._find_faculty(entities.get("faculty_slug") or entities.get("facultad"))
            if not faculty:
                return None
            careers = [career["nombre"] for career in faculty.get("carreras", [])]
            return self._with_career_closure(
                f"{faculty['nombre']} cuenta con carreras como {self._join_items(careers)}."
            )
        if intent == "consulta_facultad_de_carrera":
            career = self._find_career(entities.get("career") or entities.get("carrera"))
            if not career:
                return self._with_career_closure(
                    self._reply("carrera_no_encontrada", self._format_values(None, None))
                )
            faculty = self._find_faculty(career.get("facultad_slug") or career.get("facultad"))
            related = [
                item["nombre"]
                for item in (faculty or {}).get("carreras", [])
                if item.get("nombre") != career.get("nombre")
            ]
            extra = (
                f"Esta facultad también incluye la carrera de {self._join_items(related)}."
                if related
                else "Es la carrera principal registrada para esa facultad en la fuente controlada."
            )
            return self._with_career_closure(
                f"{career['nombre']} pertenece a {career.get('facultad')}. {extra}"
            )
        if intent == "consulta_carrera_especifica":
            career = self._find_career(entities.get("career") or entities.get("carrera"))
            if not career:
                return None
            reply = (
                f"{career['nombre']} pertenece a {career.get('facultad')}. "
                f"Esta carrera está relacionada con {career.get('descripcion_corta', 'su área de formación profesional')}."
            )
            if "consulta_admision" in entities.get("secondary_intents", []):
                reply = f"{reply}\n\nAdmisión: https://descubre.usil.edu.pe/landings/pregrado/admision/"
            return self._with_career_closure(reply)
        if intent == "consulta_campo_laboral":
            career = self._find_career(entities.get("career") or entities.get("carrera"))
            if not career:
                return None
            field = career.get("campo_laboral") or career.get("keywords") or []
            field_text = self._join_items(field) if isinstance(field, list) else str(field)
            return self._with_career_closure(
                f"Sobre el campo laboral de {career['nombre']}: puede relacionarse con {field_text}."
            )
        if intent == "comparacion_carrera":
            first = self._find_career(entities.get("career") or entities.get("carrera"))
            second = self._find_career(entities.get("carrera_comparada"))
            if first and second:
                return self._with_career_closure(
                    f"{first['nombre']} y {second['nombre']} pertenecen a "
                    f"{first.get('facultad')} y se diferencian por su enfoque. "
                    "Para comparar mallas, cursos o duración, revisa la información oficial."
                )
        return None

    def _find_faculty(self, name: str | None) -> dict[str, Any] | None:
        if not name:
            return None
        target = SemanticEngine.normalize(name)
        for faculty in self.faculties:
            aliases = [faculty.get("nombre", ""), faculty.get("slug", ""), *faculty.get("keywords", [])]
            if target in {SemanticEngine.normalize(alias) for alias in aliases}:
                return faculty
        return None

    def _with_career_closure(self, text: str) -> str:
        variants = self.replies.get("cierres_carreras") or []
        closure = random.choice(variants) if variants else self.settings.portal_oficial_url
        return self._sanitize(f"{text}\n\n{closure}", "")

    @staticmethod
    def _join_items(items: list[str]) -> str:
        values = [str(item).strip() for item in items if str(item).strip()]
        if len(values) <= 1:
            return "".join(values)
        return f"{', '.join(values[:-1])} y {values[-1]}"

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
