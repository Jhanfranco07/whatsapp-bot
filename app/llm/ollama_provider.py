import requests

from app.config import get_settings
from app.llm.provider import (
    LLMResponseError,
    LLMResult,
    LLMUnavailableError,
    LLMProvider,
)


class OllamaProvider(LLMProvider):
    def __init__(self, session=None):
        self.settings = get_settings()
        self.session = session or requests.Session()

    def generate(self, prompt: str) -> LLMResult:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "think": self.settings.ollama_think,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "num_predict": self.settings.ollama_max_tokens,
            },
        }
        try:
            response = self.session.post(
                url, json=payload, timeout=self.settings.ollama_timeout
            )
            response.raise_for_status()
        except requests.ConnectionError as error:
            raise LLMUnavailableError(
                f"Ollama no está ejecutándose en {self.settings.ollama_base_url}"
            ) from error
        except requests.Timeout as error:
            raise LLMUnavailableError(
                f"Ollama excedió el timeout de {self.settings.ollama_timeout} segundos"
            ) from error
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else "desconocido"
            raise LLMUnavailableError(
                f"Ollama respondió con error HTTP {status}"
            ) from error

        try:
            data = response.json()
            text = data["response"].strip()
        except (ValueError, KeyError, AttributeError) as error:
            raise LLMResponseError("Ollama devolvió una respuesta JSON inválida") from error
        if not text:
            raise LLMResponseError("Ollama devolvió una respuesta vacía")
        return LLMResult(text, "ollama", self.settings.ollama_model, data)

    def health(self) -> dict:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/tags"
        try:
            response = self.session.get(url, timeout=min(self.settings.ollama_timeout, 10))
            response.raise_for_status()
            models = [item.get("name") for item in response.json().get("models", [])]
        except requests.RequestException as error:
            raise LLMUnavailableError(
                f"Ollama no está ejecutándose en {self.settings.ollama_base_url}"
            ) from error
        return {
            "ok": True,
            "provider": "ollama",
            "model": self.settings.ollama_model,
            "model_available": self.settings.ollama_model in models,
        }
