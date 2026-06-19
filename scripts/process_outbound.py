import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal
from app.services.outbound_queue_service import OutboundQueueService
from app.utils.logger import configure_logging


configure_logging()
logger = logging.getLogger(__name__)


def process_once() -> dict:
    with SessionLocal() as db:
        return OutboundQueueService(db).dispatch_pending(limit=1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Mantiene el worker procesando la cola continuamente.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=1,
        help="Segundos de espera cuando no hay mensajes listos.",
    )
    parser.add_argument(
        "--sent-delay",
        type=float,
        default=2,
        help="Segundos entre dos envíos consecutivos.",
    )
    args = parser.parse_args()

    while True:
        try:
            summary = process_once()
            if summary["processed"]:
                print(summary, flush=True)
                time.sleep(max(0, args.sent_delay))
            elif not args.watch:
                print(summary)
                break
            else:
                time.sleep(max(0.2, args.poll))
        except KeyboardInterrupt:
            print("Worker detenido.")
            break
        except Exception:
            logger.exception("Error procesando la cola saliente")
            if not args.watch:
                raise
            time.sleep(max(1, args.poll))
