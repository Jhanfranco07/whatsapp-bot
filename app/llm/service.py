import json
import logging
import re
from pathlib import Path

import httpx

from app.config import get_settings
from app.llm.ollama_provider import OllamaProvider
from app.llm.prompts import UNIVERSITY_ASSISTANT_PROMPT
from app.llm.provider import LLMResponseError

logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "saludo",
    "consulta_carreras",
    "consulta_carrera_especifica",
    "consulta_campo_laboral",
    "comparacion_carrera",
    "consulta_admision",
    "consulta_costos",
    "consulta_campus",
    "consulta_modalidad",
    "consulta_institucional",
    "agradecimiento",
    "despedida",
    "detener_conversacion",
    "ruido_conversacional",
    "fuera_de_alcance",
    "no_entendido",
}

RESPONSE_KEYS = {
    "saludo": "saludo",
    "consulta_carreras": "lista_carreras",
    "consulta_carrera_especifica": "info_carrera",
    "consulta_campo_laboral": "campo_laboral",
    "comparacion_carrera": "carrera_similar",
    "consulta_admision": "admision",
    "consulta_costos": "costos",
    "consulta_campus": "campus",
    "consulta_modalidad": "modalidad",
    "consulta_institucional": "institucional",
    "agradecimiento": "agradecimiento",
    "despedida": "despedida",
    "detener_conversacion": "detener_conversacion",
    "ruido_conversacional": "silencio",
    "fuera_de_alcance": "fuera_de_alcance",
    "no_entendido": "fallback",
}


class LLMService:
    def __init__(self, provider=None):
        self.settings = get_settings()
        self.provider = provider or self._build_provider()
        data_path = Path(__file__).resolve().parents[1] / "data" / "institucion.json"
        self.institution_context = data_path.read_text(encoding="utf-8")

    @property
    def enabled(self):
        return self.settings.ollama_enabled and self.settings.llm_provider == "ollama"

    def classify(self, message: str):
        if not self.enabled:
            return None
        prompt = UNIVERSITY_ASSISTANT_PROMPT.replace("{message}", message)
        prompt = prompt.replace("{context}", self.institution_context)
        result = self.provider.generate(prompt)
        return self._validate_contract(self._parse_json(result.text))

    def health(self):
        if not self.enabled:
            return {"ok": True, "enabled": False, "provider": self.settings.llm_provider}
        return {"enabled": True, **self.provider.health()}

    async def generate_response(
        self,
        user_message: str,
        intent: str,
        context: dict,
    ) -> dict:
        """Redacta la respuesta final mediante el modo conversacional de Ollama."""
        if not self.enabled:
            return self._empty_generation()

        from app.llm.prompts import build_system_prompt

        system_prompt = build_system_prompt(context)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend([
            {"role": turn["role"], "content": turn["content"]}
            for turn in context.get("historial", [])
            if turn.get("role") in {"user", "assistant"} and turn.get("content")
        ])
        messages.append({"role": "user", "content": user_message})
        payload = {
            "model": self.settings.ollama_model,
            "system": system_prompt,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": {
                "type": "object",
                "properties": {
                    "response": {"type": "string"},
                    "should_reply": {"type": "boolean"},
                    "stop_bot": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "entities": {"type": "object"},
                },
                "required": [
                    "response",
                    "should_reply",
                    "stop_bot",
                    "confidence",
                    "entities",
                ],
            },
            "options": {
                "temperature": 0.45,
                "num_predict": self.settings.ollama_max_tokens,
            },
        }
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.settings.ollama_timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                raw = response.json().get("message", {}).get("content", "")
                return self._parse_and_validate(
                    raw,
                    intent,
                    allow_emojis=self._contains_emoji(user_message),
                    has_history=bool(context.get("historial")),
                )
        except Exception as error:
            logger.warning("Ollama generate_response falló: %s", error)
            return self._empty_generation()

    def _build_provider(self):
        if self.settings.llm_provider == "ollama":
            return OllamaProvider()
        raise ValueError(f"Proveedor LLM no soportado: {self.settings.llm_provider}")

    @staticmethod
    def _validate_contract(data):
        intent = data.get("intent")
        if intent not in ALLOWED_INTENTS:
            intent = "no_entendido"

        raw_entities = data.get("entities")
        raw_entities = raw_entities if isinstance(raw_entities, dict) else {}
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        if intent == "consulta_carrera_especifica" and not raw_entities.get("carrera"):
            intent = "no_entendido"

        return {
            "intent": intent,
            "confidence": min(max(confidence, 0.0), 1.0),
            "classifier": "ollama",
            "entities": {
                "carrera": raw_entities.get("carrera"),
                "tema": raw_entities.get("tema"),
            },
            "response": str(data.get("response") or "").strip(),
            "response_key": RESPONSE_KEYS[intent],
            "should_reply": intent not in {"ruido_conversacional", "fuera_de_alcance"},
            "should_escalate": False,
            "stop_bot": intent == "detener_conversacion",
        }

    @staticmethod
    def _parse_json(text):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise LLMResponseError("Ollama no devolvió JSON válido") from error
        if not isinstance(data, dict):
            raise LLMResponseError("Ollama debe devolver un objeto JSON")
        return data

    @staticmethod
    def _empty_generation():
        return {
            "response": None,
            "should_reply": True,
            "stop_bot": False,
            "confidence": 0.0,
            "entities": {},
        }

    def _parse_and_validate(
        self,
        raw: str,
        intent: str,
        allow_emojis: bool = True,
        has_history: bool = False,
    ) -> dict:
        match = re.search(r"\{.*\}", str(raw), re.DOTALL)
        if not match:
            response = self._sanitize_response(
                str(raw), allow_emojis=allow_emojis, has_history=has_history
            )
            if not response:
                return self._empty_generation()
            return {
                "response": response,
                "should_reply": True,
                "stop_bot": False,
                "confidence": 0.5,
                "entities": {},
            }
        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError:
            return self._empty_generation()
        if not isinstance(parsed, dict):
            return self._empty_generation()

        parsed["stop_bot"] = False
        parsed["should_reply"] = bool(parsed.get("should_reply", True))
        try:
            confidence = float(parsed.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        parsed["confidence"] = max(0.0, min(1.0, confidence))
        parsed["entities"] = (
            parsed["entities"] if isinstance(parsed.get("entities"), dict) else {}
        )
        response = parsed.get("response")
        if not isinstance(response, str) or not response.strip():
            parsed["response"] = None
        else:
            response = self._sanitize_response(
                response, allow_emojis=allow_emojis, has_history=has_history
            )
            parsed["response"] = response
        return parsed

    @staticmethod
    def _contains_emoji(text: str) -> bool:
        return bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", str(text)))

    @staticmethod
    def _remove_emojis(text: str) -> str:
        return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text).strip()

    @classmethod
    def _sanitize_response(cls, text: str, allow_emojis: bool, has_history: bool) -> str:
        response = str(text).strip()
        response = re.sub(r"```(?:json)?|```", "", response, flags=re.IGNORECASE)
        response = response.replace("**", "").replace("__", "")
        response = re.sub(r"(?m)^\s*#{1,6}\s*", "", response)
        if has_history:
            response = re.sub(
                r"^(?:¡?hola[!,.]?\s*|buenos días[!,.]?\s*|buenas tardes[!,.]?\s*)",
                "",
                response,
                flags=re.IGNORECASE,
            )
        if not allow_emojis:
            response = cls._remove_emojis(response)
        response = re.sub(r"[ \t]+\n", "\n", response)
        response = re.sub(r"\n{3,}", "\n\n", response).strip()
        if len(response) <= 800:
            return response
        shortened = response[:780].rstrip()
        boundaries = [
            shortened.rfind("."),
            shortened.rfind("?"),
            shortened.rfind("!"),
            shortened.rfind("\n"),
        ]
        boundary = max(boundaries)
        if boundary >= 480:
            shortened = shortened[: boundary + 1].rstrip()
        return shortened + "..."
