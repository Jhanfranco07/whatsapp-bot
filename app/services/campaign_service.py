import logging

from app.database.repositories import ContactRepository, MessageRepository, create_campaign_record
from app.whatsapp.sender import get_whatsapp_provider


logger = logging.getLogger(__name__)

MESSAGE_TEMPLATE = (
    "¡Hola{nombre}! 😊 Somos del equipo de orientación de USIL. Vimos que te "
    "registraste para recibir información sobre nuestras carreras. Puedo ayudarte "
    "con información sobre carreras, admisión o derivarte con un asesor. Si no "
    "deseas recibir más mensajes, responde SALIR."
)


class CampaignService:
    def __init__(self, db, provider=None):
        self.db = db
        self.provider = provider or get_whatsapp_provider()
        self.contacts = ContactRepository(db)
        self.messages = MessageRepository(db)

    def send_initial(self, limit=None, phone_number=None):
        if phone_number:
            contact = self.contacts.get_by_phone(phone_number)
            contacts = (
                [contact]
                if contact
                and not contact.opt_out
                and contact.status not in ("SALIR", "NO_INTERESADO")
                else []
            )
        else:
            contacts = self.contacts.campaign_candidates()
        if limit:
            contacts = contacts[:limit]
        summary = {"sent": 0, "failed": 0, "skipped": 0}
        for contact in contacts:
            name = f", {contact.full_name}" if contact.full_name else ""
            message = MESSAGE_TEMPLATE.format(nombre=name)
            result = self.provider.send_message(contact.phone_number, message)
            create_campaign_record(self.db, contact, message, result)
            if result.success:
                self.messages.create(contact, "outbound", message)
                contact.status = "MENSAJE_ENVIADO"
                summary["sent"] += 1
            else:
                contact.status = "ERROR_ENVIO"
                summary["failed"] += 1
            self.db.commit()
        logger.info("Campaña finalizada: %s", summary)
        return summary
