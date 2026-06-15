from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import CampaignMessage, Contact, Message


class MetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self) -> dict:
        return {
            "contacts_total": self._count(Contact.id),
            "opt_out_total": self._count(Contact.id, Contact.opt_out.is_(True)),
            "stop_bot_total": self._count(Contact.id, Contact.stop_bot.is_(True)),
            "messages_inbound": self._count(Message.id, Message.direction == "inbound"),
            "messages_outbound": self._count(Message.id, Message.direction == "outbound"),
            "campaigns_sent": self._count(CampaignMessage.id, CampaignMessage.status == "sent"),
            "campaigns_failed": self._count(CampaignMessage.id, CampaignMessage.status == "failed"),
            "top_intents": self._group_count(Message.intent, limit=8),
            "top_careers": self._group_count(Contact.career_interest, limit=8),
            "status_counts": self._group_count(Contact.status, limit=12),
        }

    def _count(self, column, *where) -> int:
        query = select(func.count(column))
        for clause in where:
            query = query.where(clause)
        return int(self.db.scalar(query) or 0)

    def _group_count(self, column, limit: int) -> list[dict]:
        rows = self.db.execute(
            select(column, func.count())
            .where(column.is_not(None))
            .group_by(column)
            .order_by(func.count().desc())
            .limit(limit)
        ).all()
        return [{"value": value, "count": count} for value, count in rows]
