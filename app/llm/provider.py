from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMError(RuntimeError):
    """Error base de proveedores LLM."""


class LLMUnavailableError(LLMError):
    """El proveedor LLM no está disponible."""


class LLMResponseError(LLMError):
    """El proveedor devolvió una respuesta inválida."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    raw_response: dict = field(default_factory=dict)


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> LLMResult:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict:
        raise NotImplementedError
