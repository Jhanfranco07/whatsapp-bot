from sqlalchemy import select

from app.database.models import AdvisorRequest
from app.database.repositories import get_or_create_advisor_request


class AdvisorService:
    def __init__(self, db):
        self.db = db

    def request(self, contact, reason):
        return get_or_create_advisor_request(self.db, contact, reason)

    def list(self, status=None):
        query = select(AdvisorRequest).order_by(AdvisorRequest.created_at.desc())
        if status:
            query = query.where(AdvisorRequest.status == status)
        return list(self.db.scalars(query))
