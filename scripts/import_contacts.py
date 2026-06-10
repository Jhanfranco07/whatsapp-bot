import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.database.connection import SessionLocal
from app.schemas.contact_schema import ContactCreate
from app.services.lead_service import LeadService


def read_rows(path):
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, dtype=str).fillna("")
        frame = frame.rename(
            columns={
                "COMPLETO": "full_name",
                "CELULAR": "phone_number",
                "COLEGIO": "school",
                "GRADO": "grade",
                "CORREO": "email",
                "CARRERA": "career_interest",
                "FUENTE": "source",
            }
        )
        return frame.to_dict(orient="records")
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    rows = read_rows(Path(args.file))
    result = {"created": 0, "duplicates": 0, "errors": 0}
    with SessionLocal() as db:
        service = LeadService(db)
        for position, row in enumerate(rows, start=2):
            try:
                allowed = set(ContactCreate.model_fields)
                cleaned = {
                    key: value
                    for key, value in row.items()
                    if key in allowed and value not in ("", None)
                }
                _, created = service.create(ContactCreate(**cleaned))
                result["created" if created else "duplicates"] += 1
            except Exception as error:
                db.rollback()
                result["errors"] += 1
                print(f"Fila {position}: {error}")
    print(result)


if __name__ == "__main__":
    main()
