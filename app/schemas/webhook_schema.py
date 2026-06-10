from datetime import datetime

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    phone_number: str
    message: str = Field(min_length=1, max_length=4000)
    timestamp: datetime | None = None
    raw_payload: dict = Field(default_factory=dict)
    send_reply: bool = False


class InboundResponse(BaseModel):
    ok: bool = True
    phone_number: str
    contact_status: str
    intent: str
    entities: dict
    bot_reply: str
    reply_sent: bool = False
