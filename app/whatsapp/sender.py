from app.config import get_settings
from app.whatsapp.bridge_sender import BridgeProvider
from app.whatsapp.pywhatkit_sender import PyWhatKitProvider


def get_whatsapp_provider():
    provider = get_settings().whatsapp_provider.lower()
    if provider == "pywhatkit":
        return PyWhatKitProvider()
    if provider == "bridge":
        return BridgeProvider()
    raise ValueError(f"Proveedor WhatsApp no soportado: {provider}")
