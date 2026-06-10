from app.config import get_settings
from app.whatsapp.pywhatkit_sender import PyWhatKitProvider


def get_whatsapp_provider():
    provider = get_settings().whatsapp_provider.lower()
    if provider == "pywhatkit":
        return PyWhatKitProvider()
    raise ValueError(f"Proveedor WhatsApp no soportado: {provider}")
