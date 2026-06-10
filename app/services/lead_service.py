from app.database.repositories import ContactRepository
from app.schemas.contact_schema import ContactCreate


class LeadService:
    def __init__(self, db):
        self.db = db
        self.contacts = ContactRepository(db)

    def create(self, data: ContactCreate):
        existing = self.contacts.get_by_phone(data.phone_number)
        if existing:
            return existing, False
        contact = self.contacts.create(data)
        self.db.commit()
        self.db.refresh(contact)
        return contact, True
