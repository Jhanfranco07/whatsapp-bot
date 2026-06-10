from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phone_number: str
    direction: str
    channel: str
    message_text: str
    intent: str | None
    entities: dict | None
    created_at: datetime
