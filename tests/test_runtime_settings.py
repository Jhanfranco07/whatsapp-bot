from types import SimpleNamespace

from app.services.runtime_settings_service import RuntimeSettingsService


class FakeDb:
    def __init__(self):
        self.rows = {}

    def get(self, model, key):
        return self.rows.get(key)

    def add(self, row):
        self.rows[row.key] = row

    def commit(self):
        pass


def test_runtime_settings_use_defaults():
    values = RuntimeSettingsService(FakeDb()).all()

    assert values["campaign_default_interval_seconds"] == 60
    assert values["bot_message_debounce_seconds"] == 3


def test_runtime_settings_are_persisted():
    db = FakeDb()
    service = RuntimeSettingsService(db)

    values = service.update({"bot_message_debounce_seconds": 5})

    assert values["bot_message_debounce_seconds"] == 5
    assert db.rows["bot_message_debounce_seconds"].value == "5"


def test_runtime_settings_clamp_corrupt_persisted_value():
    db = FakeDb()
    db.rows["bot_message_debounce_seconds"] = SimpleNamespace(value="999")

    assert RuntimeSettingsService(db).get_int("bot_message_debounce_seconds") == 15
