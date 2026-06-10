"""Lanzador compatible de la campaña inicial almacenada en PostgreSQL."""

import argparse

from app.database.connection import SessionLocal
from app.services.campaign_service import CampaignService


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Envía la campaña inicial respetando bajas y opt-out."
    )
    parser.add_argument("--limite", type=int)
    parser.add_argument("--telefono")
    args = parser.parse_args()
    with SessionLocal() as db:
        print(CampaignService(db).send_initial(args.limite, args.telefono))
