from app.database.models import RuntimeSetting


class RuntimeSettingsService:
    DEFAULTS = {
        "campaign_default_interval_seconds": 60,
        "bot_message_debounce_seconds": 3,
    }

    LIMITS = {
        "campaign_default_interval_seconds": (1, 3600),
        "bot_message_debounce_seconds": (1, 15),
    }

    def __init__(self, db):
        self.db = db

    def all(self) -> dict[str, int]:
        return {key: self.get_int(key) for key in self.DEFAULTS}

    def get_int(self, key: str) -> int:
        if key not in self.DEFAULTS:
            raise ValueError(f"Configuración desconocida: {key}")
        row = self.db.get(RuntimeSetting, key)
        if not row:
            return self.DEFAULTS[key]
        try:
            value = int(row.value)
        except (TypeError, ValueError):
            return self.DEFAULTS[key]
        minimum, maximum = self.LIMITS[key]
        return min(maximum, max(minimum, value))

    def update(self, values: dict) -> dict[str, int]:
        for key, value in values.items():
            if key not in self.DEFAULTS:
                raise ValueError(f"Configuración desconocida: {key}")
            minimum, maximum = self.LIMITS[key]
            numeric_value = int(value)
            if not minimum <= numeric_value <= maximum:
                raise ValueError(f"{key} debe estar entre {minimum} y {maximum}")
            row = self.db.get(RuntimeSetting, key)
            if row:
                row.value = str(numeric_value)
            else:
                self.db.add(RuntimeSetting(key=key, value=str(numeric_value)))
        self.db.commit()
        return self.all()
