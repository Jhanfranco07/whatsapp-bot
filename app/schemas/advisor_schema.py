from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdvisorRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: UUID
    reason: str | None
    status: str
    notes: str | None
    created_at: datetime
