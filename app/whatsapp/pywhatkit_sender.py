import logging

from app.config import get_settings
from app.whatsapp.provider import SendResult, WhatsAppProvider


logger = logging.getLogger(__name__)


class PyWhatKitProvider(WhatsAppProvider):
    def __init__(self):
        self.settings = get_settings()

    def send_message(self, phone_number: str, message: str) -> SendResult:
        if self.settings.whatsapp_dry_run:
            logger.info("DRY RUN WhatsApp a %s: %s", phone_number, message)
            return SendResult(True, "pywhatkit", raw_response={"dry_run": True})
        try:
            import pywhatkit

            pywhatkit.sendwhatmsg_instantly(
                f"+{phone_number}",
                message,
                wait_time=self.settings.whatsapp_wait_time,
                tab_close=True,
                close_time=self.settings.whatsapp_close_time,
            )
            return SendResult(True, "pywhatkit")
        except Exception as error:
            logger.exception("Error al enviar con pywhatkit")
            return SendResult(False, "pywhatkit", error=str(error))
