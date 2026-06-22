from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, or_, select

from app.database.models import CampaignMessage, Contact, Conversation, Message, OutboundMessage


class AdminService:
    def __init__(self, db):
        self.db = db

    def dashboard(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        contacts_total = self._count(Contact.id)
        campaign_sent = self._count(CampaignMessage.id, CampaignMessage.status == "sent")
        campaign_failed = self._count(CampaignMessage.id, CampaignMessage.status == "failed")
        campaign_finished = campaign_sent + campaign_failed
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "range_days": days,
            "kpis": {
                "contacts_total": contacts_total,
                "contacts_active": self._count(Contact.id, Contact.stop_bot.is_(False)),
                "opt_out_total": self._count(Contact.id, Contact.opt_out.is_(True)),
                "messages_inbound": self._count(Message.id, Message.direction == "inbound"),
                "messages_outbound": self._count(Message.id, Message.direction == "outbound"),
                "campaign_sent": campaign_sent,
                "campaign_failed": campaign_failed,
                "campaign_success_rate": round(
                    campaign_sent * 100 / campaign_finished, 1
                ) if campaign_finished else 0,
                "queue_pending": self._count(
                    OutboundMessage.id,
                    OutboundMessage.status.in_(("pending", "retrying")),
                ),
            },
            "queue_by_status": self._group_count(OutboundMessage.status, 10),
            "contacts_by_status": self._group_count(Contact.status, 12),
            "top_intents": self._group_count(Message.intent, 8),
            "top_careers": self._group_count(Contact.career_interest, 8),
            "daily_activity": self._daily_activity(since),
            "campaigns": self.campaigns(limit=8),
            "recent_queue": self.queue(limit=8),
            "recent_conversations": self.conversations(limit=8),
        }

    def campaigns(self, limit: int = 30) -> list[dict]:
        rows = self.db.execute(
            select(
                CampaignMessage.campaign_name,
                func.count(CampaignMessage.id).label("total"),
                func.sum(case((CampaignMessage.status == "sent", 1), else_=0)).label("sent"),
                func.sum(case((CampaignMessage.status == "failed", 1), else_=0)).label("failed"),
                func.sum(case((CampaignMessage.status == "pending", 1), else_=0)).label("pending"),
                func.sum(case((CampaignMessage.status == "retrying", 1), else_=0)).label("retrying"),
                func.sum(case((CampaignMessage.status == "paused", 1), else_=0)).label("paused"),
                func.sum(case((CampaignMessage.status == "cancelled", 1), else_=0)).label("cancelled"),
                func.max(CampaignMessage.interval_seconds).label("interval_seconds"),
                func.min(CampaignMessage.created_at).label("created_at"),
                func.max(CampaignMessage.sent_at).label("last_sent_at"),
            )
            .group_by(CampaignMessage.campaign_name)
            .order_by(func.max(CampaignMessage.created_at).desc())
            .limit(limit)
        ).all()
        result = []
        for row in rows:
            total = int(row.total or 0)
            sent = int(row.sent or 0)
            failed = int(row.failed or 0)
            finished = sent + failed
            result.append({
                "name": row.campaign_name or "Sin nombre",
                "total": total,
                "sent": sent,
                "failed": failed,
                "pending": int(row.pending or 0),
                "retrying": int(row.retrying or 0),
                "paused": int(row.paused or 0),
                "cancelled": int(row.cancelled or 0),
                "interval_seconds": int(row.interval_seconds or 60),
                "status": self._campaign_status(row),
                "success_rate": round(sent * 100 / finished, 1) if finished else 0,
                "created_at": self._iso(row.created_at),
                "last_sent_at": self._iso(row.last_sent_at),
            })
        return result

    def queue(self, limit: int = 50, status: str | None = None) -> list[dict]:
        query = select(OutboundMessage, Contact.full_name).join(
            Contact, Contact.id == OutboundMessage.contact_id
        )
        if status:
            query = query.where(OutboundMessage.status == status)
        query = query.order_by(OutboundMessage.created_at.desc()).limit(limit)
        return [
            {
                "id": str(item.id),
                "contact_name": name,
                "phone_number": item.phone_number,
                "message_text": item.message_text,
                "status": item.status,
                "source": item.source,
                "priority": item.priority,
                "attempts": item.attempts,
                "max_attempts": item.max_attempts,
                "scheduled_at": self._iso(item.scheduled_at),
                "sent_at": self._iso(item.sent_at),
                "error_message": item.error_message,
            }
            for item, name in self.db.execute(query).all()
        ]

    def conversations(self, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            select(Conversation, Contact)
            .join(Contact, Contact.id == Conversation.contact_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "contact_id": str(contact.id),
                "contact_name": contact.full_name,
                "phone_number": contact.phone_number,
                "status": contact.status,
                "intent": contact.last_intent,
                "last_user_message": conversation.last_user_message,
                "last_bot_message": conversation.last_bot_message,
                "updated_at": self._iso(conversation.updated_at),
                "stop_bot": contact.stop_bot,
            }
            for conversation, contact in rows
        ]

    def contacts(
        self,
        limit: int = 100,
        search: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        query = select(Contact)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(or_(
                Contact.full_name.ilike(pattern),
                Contact.phone_number.ilike(pattern),
                Contact.email.ilike(pattern),
            ))
        if status:
            query = query.where(Contact.status == status)
        query = query.order_by(Contact.updated_at.desc()).limit(limit)
        return [
            {
                "id": str(contact.id),
                "full_name": contact.full_name,
                "phone_number": contact.phone_number,
                "email": contact.email,
                "school": contact.school,
                "career_interest": contact.career_interest,
                "source": contact.source,
                "status": contact.status,
                "opt_out": contact.opt_out,
                "stop_bot": contact.stop_bot,
                "last_intent": contact.last_intent,
                "last_message_at": self._iso(contact.last_message_at),
                "created_at": self._iso(contact.created_at),
            }
            for contact in self.db.scalars(query)
        ]

    def update_contact(self, contact_id: UUID, values: dict) -> dict | None:
        contact = self.db.get(Contact, contact_id)
        if not contact:
            return None
        for field, value in values.items():
            setattr(contact, field, value)
        if values.get("opt_out") is True:
            contact.stop_bot = True
        self.db.commit()
        return self.contacts(limit=1, search=contact.phone_number)[0]

    def cancel_campaign(self, campaign_name: str) -> dict:
        records = list(self.db.scalars(
            select(CampaignMessage).where(
                CampaignMessage.campaign_name == campaign_name,
                CampaignMessage.status.in_(("pending", "retrying", "paused")),
            )
        ))
        record_ids = {str(record.id) for record in records}
        queue_rows = []
        if record_ids:
            queue_rows = list(self.db.scalars(
                select(OutboundMessage).where(
                    OutboundMessage.source == "campaign",
                    OutboundMessage.source_id.in_(record_ids),
                    OutboundMessage.status.in_(("pending", "retrying", "paused")),
                )
            ))
        for record in records:
            record.status = "cancelled"
            record.error_message = "cancelled by administrator"
        for item in queue_rows:
            item.status = "cancelled"
            item.error_message = "cancelled by administrator"
            item.locked_at = None
        self.db.commit()
        return {"ok": True, "cancelled": len(queue_rows)}

    def control_campaign(
        self,
        campaign_name: str,
        action: str,
        interval_seconds: int | None = None,
    ) -> dict:
        records = list(self.db.scalars(
            select(CampaignMessage)
            .where(
                CampaignMessage.campaign_name == campaign_name,
                CampaignMessage.status.in_(("pending", "retrying", "paused")),
            )
            .order_by(CampaignMessage.created_at)
        ))
        record_by_id = {str(record.id): record for record in records}
        queue_rows = list(self.db.scalars(
            select(OutboundMessage)
            .where(
                OutboundMessage.source == "campaign",
                OutboundMessage.source_id.in_(record_by_id),
                OutboundMessage.status.in_(("pending", "retrying", "paused")),
            )
            .order_by(OutboundMessage.scheduled_at, OutboundMessage.created_at)
        )) if record_by_id else []

        if action == "pause":
            for record in records:
                record.status = "paused"
            for item in queue_rows:
                item.status = "paused"
                item.locked_at = None
        elif action in {"resume", "update"}:
            if interval_seconds is None:
                interval_seconds = records[0].interval_seconds if records else 60
            now = datetime.now(timezone.utc)
            for position, item in enumerate(queue_rows):
                record = record_by_id.get(str(item.source_id))
                if record:
                    record.interval_seconds = interval_seconds
                    if record.status == "paused":
                        record.status = "pending"
                if item.status == "paused":
                    item.status = "pending"
                item.scheduled_at = now + timedelta(
                    seconds=position * interval_seconds
                )
                item.locked_at = None
        else:
            raise ValueError("Acción de campaña inválida")

        self.db.commit()
        return {
            "ok": True,
            "action": action,
            "affected": len(queue_rows),
            "interval_seconds": interval_seconds,
        }

    def _daily_activity(self, since: datetime) -> list[dict]:
        day = func.date(Message.created_at)
        rows = self.db.execute(
            select(
                day.label("day"),
                func.sum(case((Message.direction == "inbound", 1), else_=0)).label("inbound"),
                func.sum(case((Message.direction == "outbound", 1), else_=0)).label("outbound"),
            )
            .where(Message.created_at >= since)
            .group_by(day)
            .order_by(day)
        ).all()
        return [
            {"date": str(row.day), "inbound": int(row.inbound or 0), "outbound": int(row.outbound or 0)}
            for row in rows
        ]

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
        return [{"value": value, "count": int(count)} for value, count in rows]

    @staticmethod
    def _iso(value):
        return value.isoformat() if value else None

    @staticmethod
    def _campaign_status(row) -> str:
        if int(row.paused or 0):
            return "paused"
        if int(row.pending or 0) or int(row.retrying or 0):
            return "running"
        if int(row.failed or 0) and not int(row.sent or 0):
            return "failed"
        if int(row.cancelled or 0) and not int(row.sent or 0):
            return "cancelled"
        return "completed"
