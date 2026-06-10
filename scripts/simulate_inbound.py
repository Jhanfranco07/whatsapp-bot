import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal
from app.schemas.webhook_schema import InboundMessage
from app.services.conversation_service import ConversationService


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = ConversationService(db).process_inbound(
            InboundMessage(phone_number=args.phone, message=args.message)
        )
    print(f"Intent detected: {result['intent']}")
    print(f"Contact status: {result['contact_status']}")
    print(f"Bot reply: {result['bot_reply']}")
