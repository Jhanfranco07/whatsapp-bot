from fastapi.testclient import TestClient
from types import SimpleNamespace

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


def test_admin_panel_endpoint():
    response = TestClient(app).get("/admin")
    assert response.status_code == 200
    assert "Orientador USIL" in response.text
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_admin_panel_static_assets():
    client = TestClient(app)

    assert client.get("/static/admin/styles.css").status_code == 200
    assert client.get("/static/admin/app.js").status_code == 200


def test_admin_knowledge_endpoint():
    response = TestClient(app).get("/admin/knowledge")
    assert response.status_code == 200
    assert "entries" in response.json()


def test_semantic_health_endpoint():
    response = TestClient(app).get("/health/llm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["engine"] == "tfidf_semantic"
    assert payload["intents_loaded"] >= 33
    assert payload["probe"] == {
        "text": "hola",
        "intent": "saludo",
        "confidence": 1.0,
    }


def test_removed_human_request_endpoint_does_not_exist():
    response = TestClient(app).get("/advisor-requests")
    assert response.status_code == 404


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


def test_simulation_requires_admin_key_when_configured(monkeypatch):
    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(main_module.settings, "admin_api_key", "correcta")
    client = TestClient(app)

    response = client.post(
        "/simulate/inbound",
        json={"phone_number": "999999999", "message": "hola"},
    )

    app.dependency_overrides.clear()
    monkeypatch.setattr(main_module.settings, "admin_api_key", "")
    assert response.status_code == 401


def test_contacts_require_admin_key_when_configured(monkeypatch):
    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(main_module.settings, "admin_api_key", "correcta")

    response = TestClient(app).get("/contacts")

    app.dependency_overrides.clear()
    monkeypatch.setattr(main_module.settings, "admin_api_key", "")
    assert response.status_code == 401


def test_webhook_duplicate_is_acknowledged_without_new_reply(monkeypatch):
    class ExistingMessages:
        def __init__(self, db):
            pass

        def get_by_external_id(self, external_id):
            return SimpleNamespace(
                phone_number="51999999999",
                intent="saludo",
            )

    class ExistingContacts:
        def __init__(self, db):
            pass

        def get_by_phone(self, phone):
            return SimpleNamespace(status="RESPONDIO")

    app.dependency_overrides[get_db] = fake_db
    monkeypatch.setattr(main_module.settings, "inbound_api_key", "")
    monkeypatch.setattr(main_module, "MessageRepository", ExistingMessages)
    monkeypatch.setattr(main_module, "ContactRepository", ExistingContacts)
    client = TestClient(app)

    response = client.post(
        "/webhooks/whatsapp/inbound",
        json={
            "phone_number": "999999999",
            "message": "hola",
            "raw_payload": {"whatsapp_message_id": "wamid-1"},
        },
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["classification_source"] == "idempotency"
    assert response.json()["should_reply"] is False
