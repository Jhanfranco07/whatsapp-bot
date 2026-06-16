import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal
from app.services.outbound_queue_service import OutboundQueueService


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(OutboundQueueService(db).dispatch_pending(args.limit))
