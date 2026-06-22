from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.admin_service import AdminService


class FakeDb:
    def __init__(self, records, queue_rows):
        self.results = [records, queue_rows]
        self.committed = False

    def scalars(self, query):
        return iter(self.results.pop(0))

    def commit(self):
        self.committed = True


def campaign_rows(status="pending"):
    record_id = uuid4()
    now = datetime.now(timezone.utc)
    record = SimpleNamespace(
        id=record_id,
        status=status,
        interval_seconds=60,
        created_at=now,
    )
    queued = SimpleNamespace(
        source_id=str(record_id),
        status=status,
        scheduled_at=now,
        created_at=now,
        locked_at=now,
    )
    return record, queued


def test_pause_campaign_excludes_pending_rows():
    record, queued = campaign_rows()
    db = FakeDb([record], [queued])

    result = AdminService(db).control_campaign("admision", "pause")

    assert result["affected"] == 1
    assert record.status == "paused"
    assert queued.status == "paused"
    assert queued.locked_at is None
    assert db.committed is True


def test_resume_campaign_applies_new_interval():
    record, queued = campaign_rows("paused")
    db = FakeDb([record], [queued])

    result = AdminService(db).control_campaign(
        "admision", "resume", interval_seconds=25
    )

    assert result["interval_seconds"] == 25
    assert record.status == "pending"
    assert record.interval_seconds == 25
    assert queued.status == "pending"
