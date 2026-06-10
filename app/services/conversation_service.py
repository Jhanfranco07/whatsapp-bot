import logging
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
from app.whatsapp.sender import get_whatsapp_provider


logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, db, provider=None):
        self.db = db
        self.contacts = ContactRepository(db)
        self.messages = MessageRepository(db)
        self.classifier = IntentClassifier()
        self.chatbot = ChatbotService()
        self.advisors = AdvisorService(db)
        self.provider = provider or get_whatsapp_provider()

    def process_inbound(self, payload):
        contact, created = self.contacts.get_or_create(payload.phone_number, source="webhook")
        context = get_conversation_context(self.db, contact.id)
        intent, entities = self.classifier.classify(payload.message)
        if entities.get("name"):
            contact.full_name = entities["name"]
        result = self.chatbot.respond(intent, entities, contact, context)

        self.messages.create(contact, "inbound", payload.message, intent, entities, payload.raw_payload)
        self.messages.create(contact, "outbound", result.bot_reply, intent, entities)

        contact.status = result.new_status
        contact.opt_out = result.opt_out or contact.opt_out
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
        if intent == "consulta_becas":
            context["last_topic"] = "becas"
        if intent == "consulta_portal":
            context["portal_shared"] = True
        if result.requires_advisor:
            context["advisor_requested"] = True
        context["last_intent"] = intent
        if result.advisor_request_needed:
            self.advisors.request(contact, result.advisor_reason)

        upsert_conversation(
            self.db, contact, payload.message, result.bot_reply, result.new_status, context
        )

        reply_sent = False
        if payload.send_reply:
            send_result = self.provider.send_message(contact.phone_number, result.bot_reply)
            reply_sent = send_result.success

        self.db.commit()
        logger.info("Inbound procesado: phone=%s intent=%s created=%s", contact.phone_number, intent, created)
        return {
            "ok": True,
            "phone_number": contact.phone_number,
            "contact_status": contact.status,
            "intent": intent,
            "entities": entities,
            "bot_reply": result.bot_reply,
            "reply_sent": reply_sent,
        }
