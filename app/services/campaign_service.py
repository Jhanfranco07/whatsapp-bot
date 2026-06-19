import logging
from datetime import datetime, timedelta, timezone

from app.database.repositories import ContactRepository, create_campaign_record
from app.services.contact_states import CAMPAIGN_EXCLUDED_STATES
from app.services.outbound_queue_service import OutboundPriority, OutboundQueueService
from app.whatsapp.sender import get_whatsapp_provider


logger = logging.getLogger(__name__)

MESSAGE_TEMPLATE = (
    "¡Hola{nombre}! Somos del equipo de orientación de USIL. Vimos que te "
    "registraste para recibir información sobre nuestras carreras. Puedo ayudarte "
    "con información sobre carreras, admisión o canales oficiales de contacto. Si no "
    "deseas recibir más mensajes, responde SALIR."
)


class CampaignService:
    def __init__(self, db, provider=None):
        self.db = db
        self.provider = provider or get_whatsapp_provider()
        self.contacts = ContactRepository(db)
        self.outbound_queue = OutboundQueueService(db, self.provider)

    def send_initial(self, limit=None, phone_number=None, delay_seconds=60):
        campaign_name = "campaña_inicial"
        if phone_number:
            contact = self.contacts.get_by_phone(phone_number)
            contacts = (
                [contact]
                if contact
                and not contact.opt_out
                and not getattr(contact, "stop_bot", False)
                and contact.status not in CAMPAIGN_EXCLUDED_STATES
                and not self.contacts.has_campaign_record(contact.id, campaign_name)
                else []
            )
        else:
            contacts = self.contacts.campaign_candidates(campaign_name)
        if limit:
            contacts = contacts[:limit]

        summary = {"queued": 0, "sent": 0, "failed": 0, "skipped": 0}
        start_at = datetime.now(timezone.utc)
        for position, contact in enumerate(contacts):
            name = f", {contact.full_name}" if contact.full_name else ""
            message = MESSAGE_TEMPLATE.format(nombre=name)
            record = create_campaign_record(
                self.db,
                contact,
                message,
                campaign_name=campaign_name,
            )
            self.db.flush()
            self.outbound_queue.enqueue(
                contact,
                message,
                source="campaign",
                source_id=str(record.id),
                priority=OutboundPriority.CAMPAIGN,
                scheduled_at=start_at + timedelta(seconds=position * delay_seconds),
            )
            summary["queued"] += 1
            self.db.commit()

        logger.info("Campaña encolada: %s", summary)
        return summary
