from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class ContactCreate(BaseModel):
    full_name: str | None = None
    phone_number: str
    school: str | None = None
    grade: str | None = None
    email: EmailStr | None = None
    career_interest: str | None = None
    source: str | None = None


class ContactRead(ContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    opt_out: bool
    stop_bot: bool
    requires_advisor: bool
    last_intent: str | None
    created_at: datetime
