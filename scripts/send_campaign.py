import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.connection import SessionLocal
from app.services.campaign_service import CampaignService


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--phone", help="Envía únicamente al teléfono indicado")
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Segundos entre contactos (usa la configuración del panel si se omite)",
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        print(CampaignService(db).send_initial(args.limit, args.phone, args.delay))
