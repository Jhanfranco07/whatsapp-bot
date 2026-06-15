import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone

from app.database.repositories import (
    ContactRepository,
    MessageRepository,
    get_conversation_context,
    upsert_conversation,
)
from app.services.advisor_service import AdvisorService
from app.services.chatbot_service import ChatbotService
from app.services.intent_classifier import IntentClassifier
from app.utils.phone_utils import normalize_phone
from app.whatsapp.sender import get_whatsapp_provider


logger = logging.getLogger(__name__)


class ConversationService:
    _contact_locks = defaultdict(asyncio.Lock)

    def __init__(self, db, provider=None):
        self.db = db
        self.contacts = ContactRepository(db)
        self.messages = MessageRepository(db)
        self.classifier = IntentClassifier()
        self.chatbot = ChatbotService()
        self.advisors = AdvisorService(db)
        self.provider = provider or get_whatsapp_provider()

    def process_inbound(self, payload):
        """Entrada síncrona conservada para scripts y compatibilidad."""
        return asyncio.run(self.process_inbound_async(payload))

    async def process_inbound_async(self, payload):
        phone_number = normalize_phone(payload.phone_number)
        async with self._contact_locks[phone_number]:
            return await self._process_inbound_async(payload)

    async def _process_inbound_async(self, payload):
        contact, created = self.contacts.get_or_create(payload.phone_number, source="webhook")
        context = get_conversation_context(self.db, contact.id)
        if getattr(contact, "stop_bot", False):
            self.messages.create(
                contact,
                "inbound",
                payload.message,
                "bot_detenido",
                {"stop_bot": True},
                payload.raw_payload,
            )
            contact.last_message_at = payload.timestamp or datetime.now(timezone.utc)
            context["last_intent"] = "bot_detenido"
            upsert_conversation(
                self.db, contact, payload.message, None, contact.status, context
            )
            self.db.commit()
            logger.info("Mensaje guardado sin respuesta: phone=%s stop_bot=true", contact.phone_number)
            return {
                "ok": True,
                "phone_number": contact.phone_number,
                "contact_status": contact.status,
                "intent": "bot_detenido",
                "entities": {"stop_bot": True},
                "classification_source": "system",
                "bot_reply": None,
                "should_reply": False,
                "reply_sent": False,
            }
        intent, entities = self.classifier.classify(payload.message, context)
        classification_source = entities.pop("classification_source", "rules")
        if entities.get("name"):
            contact.full_name = entities["name"]
        result = self.chatbot.respond(intent, entities, contact, context)
        bot_reply, generated_should_reply = await self.chatbot.generate_response(
            intent=intent,
            entities=entities,
            contact_id=contact.id,
            user_message=payload.message,
            conversation_context=context,
            contact=contact,
        )
        result.bot_reply = bot_reply or ""
        result.should_reply = generated_should_reply

        self.messages.create(contact, "inbound", payload.message, intent, entities, payload.raw_payload)
        should_reply = result.should_reply and entities.get("should_reply", True)
        if should_reply:
            self.messages.create(contact, "outbound", result.bot_reply, intent, entities)

        contact.status = result.new_status
        contact.opt_out = result.opt_out or contact.opt_out
        contact.stop_bot = (
            getattr(contact, "stop_bot", False)
            or entities.get("stop_bot", False)
            or intent == "detener_conversacion"
        )
        contact.requires_advisor = result.requires_advisor or contact.requires_advisor
        contact.last_intent = intent
        contact.last_message_at = payload.timestamp or datetime.now(timezone.utc)
        if entities.get("career"):
            contact.career_interest = entities["career"]
            context["last_career"] = entities["career"]
            context["last_topic"] = "carrera"
        if entities.get("name"):
            context["detected_name"] = entities["name"]
        if intent == "consulta_admision":
            context["last_topic"] = "admision"
        if intent in {
            "comparacion_carrera",
            "consulta_malla",
            "consulta_duracion",
            "consulta_modalidad",
            "consulta_costos",
            "consulta_campus",
            "consulta_internacionalidad",
        }:
            context["last_topic"] = intent
        if intent == "consulta_becas":
            context["last_topic"] = "becas"
        if intent == "consulta_portal":
            context["portal_shared"] = True
        if result.requires_advisor:
            context["advisor_requested"] = True
        context["last_intent"] = intent
        history = list(context.get("historial", []))
        history.append({"role": "user", "content": payload.message})
        if should_reply and result.bot_reply:
            history.append({"role": "assistant", "content": result.bot_reply})
        context["historial"] = history[-3:]
        if result.advisor_request_needed:
            self.advisors.request(contact, result.advisor_reason)

        upsert_conversation(
            self.db,
            contact,
            payload.message,
            result.bot_reply if should_reply else None,
            result.new_status,
            context,
        )

        reply_sent = False
        if payload.send_reply and should_reply:
            send_result = self.provider.send_message(contact.phone_number, result.bot_reply)
            reply_sent = send_result.success

        self.db.commit()
        logger.info(
            "Inbound procesado: phone=%s intent=%s source=%s created=%s",
            contact.phone_number,
            intent,
            classification_source,
            created,
        )
        return {
            "ok": True,
            "phone_number": contact.phone_number,
            "contact_status": contact.status,
            "intent": intent,
            "entities": entities,
            "classification_source": classification_source,
            "bot_reply": result.bot_reply if should_reply else None,
            "should_reply": should_reply,
            "reply_sent": reply_sent,
        }
