from types import SimpleNamespace

from app.services.campaign_service import CampaignService
from app.whatsapp.bridge_sender import BridgeProvider
from app.whatsapp.provider import SendResult
from app.whatsapp.pywhatkit_sender import PyWhatKitProvider


class FakeProvider:
    def __init__(self):
        self.sent = []

    def send_message(self, phone, message):
        self.sent.append((phone, message))
        return SendResult(True, "fake")


class FakeDb:
    def add(self, item):
        pass

    def flush(self):
        pass

    def commit(self):
        pass


def test_dry_run_does_not_import_or_send(monkeypatch):
    provider = PyWhatKitProvider()
    monkeypatch.setattr(provider.settings, "whatsapp_dry_run", True)
    result = provider.send_message("51999999999", "hola")
    assert result.success is True
    assert result.raw_response == {"dry_run": True}


def test_bridge_provider_sends_through_persistent_session(monkeypatch):
    class Response:
        ok = True

        @staticmethod
        def json():
            return {"ok": True, "message_id": "message-1"}

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return Response()

    provider = BridgeProvider()
    monkeypatch.setattr("app.whatsapp.bridge_sender.requests.post", fake_post)
    result = provider.send_message("51999999999", "hola")

    assert result.success is True
    assert result.provider == "bridge"
    assert captured["json"] == {"phone_number": "51999999999", "message": "hola"}


def test_campaign_only_uses_filtered_candidates():
    allowed = SimpleNamespace(
        id="1", full_name="Ana", phone_number="51999999999", status="NUEVO"
    )
    provider = FakeProvider()
    service = CampaignService(FakeDb(), provider)
    service.contacts = SimpleNamespace(campaign_candidates=lambda: [allowed])
    service.messages = SimpleNamespace(create=lambda *args, **kwargs: None)

    result = service.send_initial()

    assert result["sent"] == 1
    assert provider.sent[0][0] == "51999999999"
    assert allowed.status == "CONTACTADO"


def test_campaign_can_target_phone():
    target = SimpleNamespace(
        id="2",
        full_name="Fiorella",
        phone_number="51984738899",
        status="NUEVO",
        opt_out=False,
        stop_bot=False,
    )
    provider = FakeProvider()
    service = CampaignService(FakeDb(), provider)
    service.contacts = SimpleNamespace(get_by_phone=lambda phone: target)
    service.messages = SimpleNamespace(create=lambda *args, **kwargs: None)

    result = service.send_initial(phone_number="984738899")

    assert result["sent"] == 1
    assert provider.sent[0][0] == "51984738899"


def test_campaign_does_not_target_stopped_contact():
    target = SimpleNamespace(
        id="3",
        full_name="Ana",
        phone_number="51981111111",
        status="NUEVO",
        opt_out=False,
        stop_bot=True,
    )
    provider = FakeProvider()
    service = CampaignService(FakeDb(), provider)
    service.contacts = SimpleNamespace(get_by_phone=lambda phone: target)
    service.messages = SimpleNamespace(create=lambda *args, **kwargs: None)

    result = service.send_initial(phone_number=target.phone_number)

    assert result["sent"] == 0
    assert provider.sent == []
