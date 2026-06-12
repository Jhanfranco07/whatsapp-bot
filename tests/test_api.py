from fastapi.testclient import TestClient

from app.database.connection import get_db
from app.main import app
import app.main as main_module


def fake_db():
    yield object()


class FakeConversationService:
    def __init__(self, db):
        pass

    def process_inbound(self, payload):
        return {
            "ok": True,
            "phone_number": "51999999999",
            "contact_status": "INTERESADO_CARRERA",
            "intent": "consulta_carrera_especifica",
            "entities": {"career": "Ingeniería de Sistemas"},
            "classification_source": "rules",
            "bot_reply": "Respuesta controlada",
            "reply_sent": False,
        }


def test_root_endpoint():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_simulate_inbound_endpoint(monkeypatch):
    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(main_module, "ConversationService", FakeConversationService)
    client = TestClient(app)

    response = client.post(
        "/simulate/inbound",
        json={"phone_number": "999999999", "message": "me interesa sistemas"},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["intent"] == "consulta_carrera_especifica"
    assert response.json()["classification_source"] == "rules"
    assert response.json()["bot_reply"] == "Respuesta controlada"


def test_webhook_rejects_invalid_api_key(monkeypatch):
    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(main_module.settings, "inbound_api_key", "correcta")
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp/inbound",
        headers={"X-Inbound-Api-Key": "incorrecta"},
        json={"phone_number": "999999999", "message": "hola"},
    )

    app.dependency_overrides.clear()
    monkeypatch.setattr(main_module.settings, "inbound_api_key", "")
    assert response.status_code == 401
