from typing import Protocol


class InboundReceiver(Protocol):
    """Contrato para futuros puentes como whatsapp-web.js o Baileys."""

    def receive(self) -> dict: ...
