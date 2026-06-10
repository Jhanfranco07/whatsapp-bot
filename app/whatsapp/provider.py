from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SendResult:
    success: bool
    provider: str
    error: str | None = None
    raw_response: dict | None = None


class WhatsAppProvider(ABC):
    @abstractmethod
    def send_message(self, phone_number: str, message: str) -> SendResult:
        raise NotImplementedError
