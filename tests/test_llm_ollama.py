import json
import asyncio

import pytest
import requests

from app.llm.ollama_provider import OllamaProvider
from app.llm.provider import LLMUnavailableError
from app.llm.service import LLMService
import app.llm.service as llm_service_module


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.last_url = None
        self.last_json = None
        self.last_timeout = None

    def post(self, url, json, timeout):
        self.last_url = url
        self.last_json = json
        self.last_timeout = timeout
        contract = {
            "intent": "consulta_admision",
            "confidence": 0.91,
            "classifier": "ollama",
            "entities": {"carrera": None, "campus": None},
            "response_key": "incorrecto",
            "should_reply": False,
            "should_escalate": True,
            "stop_bot": True,
        }
        return FakeResponse({"response": __import__("json").dumps(contract)})

    def get(self, url, timeout):
        return FakeResponse({"models": [{"name": "qwen3.5:0.8b"}]})


def test_ollama_generate_uses_expected_http_payload():
    session = FakeSession()
    result = OllamaProvider(session=session).generate("Clasifica este mensaje")

    assert session.last_url == "http://localhost:11434/api/generate"
    assert session.last_json == {
        "model": "qwen3.5:0.8b",
        "prompt": "Clasifica este mensaje",
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 400},
    }
    assert session.last_timeout == 120
    assert json.loads(result.text)["intent"] == "consulta_admision"


def test_llm_service_validates_simulated_ollama_contract(monkeypatch):
    service = LLMService(provider=OllamaProvider(session=FakeSession()))
    monkeypatch.setattr(service.settings, "ollama_enabled", True)
    result = service.classify("información para postular")
    assert result["intent"] == "consulta_admision"
    assert result["confidence"] == 0.91
    assert result["response_key"] == "admision"
    assert result["should_reply"] is True
    assert result["should_escalate"] is False
    assert result["stop_bot"] is False


def test_ollama_connection_error_is_clear():
    class OfflineSession:
        def post(self, url, json, timeout):
            raise requests.ConnectionError("offline")

    with pytest.raises(LLMUnavailableError, match="Ollama no está ejecutándose"):
        OllamaProvider(session=OfflineSession()).generate("hola")


def test_ollama_health_reports_model_available():
    result = OllamaProvider(session=FakeSession()).health()
    assert result["model_available"] is True


def test_invalid_intent_falls_back_to_not_understood(monkeypatch):
    class InvalidProvider:
        def generate(self, prompt):
            from app.llm.provider import LLMResult

            return LLMResult('{"intent":"presentacion_nombre"}', "fake", "fake")

    service = LLMService(provider=InvalidProvider())
    monkeypatch.setattr(service.settings, "ollama_enabled", True)
    result = service.classify("soy una persona")
    assert result["intent"] == "no_entendido"
    assert result["response_key"] == "fallback"


def test_specific_career_without_entity_falls_back(monkeypatch):
    class MissingCareerProvider:
        def generate(self, prompt):
            from app.llm.provider import LLMResult

            return LLMResult(
                '{"intent":"consulta_carrera_especifica","entities":{}}',
                "fake",
                "fake",
            )

    service = LLMService(provider=MissingCareerProvider())
    monkeypatch.setattr(service.settings, "ollama_enabled", True)
    assert service.classify("una carrera")["intent"] == "no_entendido"


def test_stop_contract_is_enforced(monkeypatch):
    class StopProvider:
        def generate(self, prompt):
            from app.llm.provider import LLMResult

            return LLMResult(
                '{"intent":"detener_conversacion","confidence":0.98,"entities":{}}',
                "fake",
                "fake",
            )

    service = LLMService(provider=StopProvider())
    monkeypatch.setattr(service.settings, "ollama_enabled", True)
    result = service.classify("basta")
    assert result["response_key"] == "detener_conversacion"
    assert result["stop_bot"] is True


def test_noise_contract_is_silent(monkeypatch):
    class NoiseProvider:
        def generate(self, prompt):
            from app.llm.provider import LLMResult

            return LLMResult(
                '{"intent":"ruido_conversacional","confidence":0.9,'
                '"entities":{},"response":"No debería enviarse"}',
                "fake",
                "fake",
            )

    service = LLMService(provider=NoiseProvider())
    monkeypatch.setattr(service.settings, "ollama_enabled", True)
    result = service.classify("jajaja")
    assert result["intent"] == "ruido_conversacional"
    assert result["should_reply"] is False
    assert result["stop_bot"] is False


def test_generate_response_uses_chat_endpoint_and_history(monkeypatch):
    captured = {}

    class AsyncResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "response": "Mira, Administración desarrolla habilidades de gestión.",
                            "should_reply": True,
                            "stop_bot": True,
                            "confidence": 0.91,
                            "entities": {"carrera": "Administración"},
                        }
                    )
                }
            }

    class AsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return AsyncResponse()

    monkeypatch.setattr(llm_service_module.httpx, "AsyncClient", AsyncClient)
    service = LLMService(provider=OllamaProvider(session=FakeSession()))
    monkeypatch.setattr(service.settings, "ollama_enabled", True)
    result = asyncio.run(
        service.generate_response(
            "¿Y qué habilidades desarrolla?",
            "consulta_carrera_especifica",
            {
                "institucion": {"nombre": "USIL"},
                "carrera_info": {"nombre": "Administración"},
                "historial": [{"role": "user", "content": "Administración"}],
                "plantilla_guia": "Explica la carrera de forma general.",
            },
        )
    )

    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["options"]["temperature"] == 0.45
    assert captured["payload"]["think"] is False
    assert captured["payload"]["messages"][0]["role"] == "system"
    assert captured["payload"]["messages"][1]["content"] == "Administración"
    assert captured["payload"]["format"]["type"] == "object"
    assert result["response"].startswith("Mira")
    assert result["stop_bot"] is False


def test_generated_response_is_truncated():
    service = LLMService(provider=OllamaProvider(session=FakeSession()))
    result = service._parse_and_validate(
        json.dumps({"response": "x" * 900, "confidence": 2, "stop_bot": True}),
        "consulta_carreras",
    )
    assert len(result["response"]) <= 783
    assert result["confidence"] == 1.0
    assert result["stop_bot"] is False


def test_generated_response_removes_emoji_when_user_did_not_use_one():
    service = LLMService(provider=OllamaProvider(session=FakeSession()))
    result = service._parse_and_validate(
        json.dumps({"response": "Te cuento que Administración desarrolla gestión 😊"}),
        "consulta_carrera_especifica",
        allow_emojis=False,
    )
    assert "😊" not in result["response"]


def test_plain_text_from_small_model_is_safely_accepted():
    service = LLMService(provider=OllamaProvider(session=FakeSession()))
    result = service._parse_and_validate(
        "¡Hola! Te cuento que **Administración** desarrolla gestión y liderazgo.",
        "consulta_carrera_especifica",
        allow_emojis=False,
        has_history=True,
    )
    assert result["response"].startswith("Te cuento")
    assert "**" not in result["response"]
    assert result["stop_bot"] is False
