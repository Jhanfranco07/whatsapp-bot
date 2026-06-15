from types import SimpleNamespace

from app.services.metrics_service import MetricsService


class FakeDb:
    def scalar(self, query):
        return 2

    def execute(self, query):
        return SimpleNamespace(all=lambda: [("saludo", 3)])


def test_metrics_summary_shape():
    summary = MetricsService(FakeDb()).summary()

    assert summary["contacts_total"] == 2
    assert summary["messages_inbound"] == 2
    assert summary["top_intents"] == [{"value": "saludo", "count": 3}]
