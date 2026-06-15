import requests

from app.config import get_settings
from app.whatsapp.provider import SendResult, WhatsAppProvider


class BridgeProvider(WhatsAppProvider):
    def __init__(self):
        self.settings = get_settings()

    def send_message(self, phone_number: str, message: str) -> SendResult:
        headers = {}
        if self.settings.inbound_api_key:
            headers["X-Inbound-Api-Key"] = self.settings.inbound_api_key
        try:
            response = requests.post(
                self.settings.bridge_send_url,
                headers=headers,
                json={"phone_number": phone_number, "message": message},
                timeout=self.settings.bridge_send_timeout,
            )
            data = response.json()
            if response.ok:
                return SendResult(True, "bridge", raw_response=data)
            return SendResult(
                False,
                "bridge",
                error=data.get("error") or f"HTTP {response.status_code}",
                raw_response=data,
            )
        except Exception as error:
            return SendResult(False, "bridge", error=str(error))
