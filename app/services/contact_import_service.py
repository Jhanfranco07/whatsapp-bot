import io
import re
import unicodedata
from pathlib import Path

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select

from app.database.models import Contact
from app.schemas.contact_schema import ContactCreate
from app.utils.phone_utils import normalize_phone


class ContactImportService:
    COLUMN_ALIASES = {
        "COMPLETO": "full_name",
        "NOMBRE": "full_name",
        "NOMBRES": "full_name",
        "NOMBRE COMPLETO": "full_name",
        "CELULAR": "phone_number",
        "TELEFONO": "phone_number",
        "WHATSAPP": "phone_number",
        "COLEGIO": "school",
        "GRADO": "grade",
        "CORREO": "email",
        "EMAIL": "email",
        "CARRERA": "career_interest",
        "FUENTE": "source",
    }

    def __init__(self, db):
        self.db = db

    def preview(self, filename: str, content: bytes) -> dict:
        frame = self._read(filename, content)
        if len(frame.index) > 5000:
            raise ValueError("El archivo supera el máximo de 5000 filas")

        mapped_columns = {}
        for original in frame.columns:
            normalized = self._column_name(original)
            mapped = self.COLUMN_ALIASES.get(normalized)
            if mapped:
                mapped_columns[str(original)] = mapped
        frame = frame.rename(columns=mapped_columns).fillna("")
        if "phone_number" not in frame.columns:
            raise ValueError("No se encontró una columna CELULAR, TELEFONO o WHATSAPP")

        existing = set(self.db.scalars(select(Contact.phone_number)))
        seen = set()
        rows = []
        summary = {"total": len(frame.index), "valid": 0, "invalid": 0, "duplicates": 0}
        allowed = set(ContactCreate.model_fields)

        for position, source in enumerate(frame.to_dict(orient="records"), start=2):
            cleaned = {
                key: str(value).strip()
                for key, value in source.items()
                if key in allowed and str(value).strip()
            }
            errors = []
            normalized_phone = None
            try:
                normalized_phone = self.normalize_peruvian_phone(
                    cleaned.get("phone_number", "")
                )
                cleaned["phone_number"] = normalized_phone
                validated = ContactCreate(**cleaned)
                cleaned = validated.model_dump(mode="json", exclude_none=True)
            except (ValueError, ValidationError) as error:
                errors.append(self._validation_message(error))

            if errors:
                status = "invalid"
                summary["invalid"] += 1
            elif normalized_phone in seen or normalized_phone in existing:
                status = "duplicate"
                summary["duplicates"] += 1
            else:
                status = "valid"
                summary["valid"] += 1
                seen.add(normalized_phone)

            rows.append({
                "row_number": position,
                "status": status,
                "errors": errors,
                "data": cleaned,
            })

        return {
            "filename": Path(filename).name,
            "columns_detected": mapped_columns,
            "summary": summary,
            "rows": rows,
        }

    @staticmethod
    def _read(filename: str, content: bytes) -> pd.DataFrame:
        suffix = Path(filename).suffix.lower()
        stream = io.BytesIO(content)
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(stream, dtype=str)
        if suffix == ".csv":
            return pd.read_csv(stream, dtype=str, sep=None, engine="python")
        raise ValueError("Formato no admitido. Usa .xlsx, .xls o .csv")

    @staticmethod
    def normalize_peruvian_phone(value: str) -> str:
        normalized = normalize_phone(value)
        if not re.fullmatch(r"519\d{8}", normalized):
            raise ValueError(
                "Debe ser un celular peruano de 9 dígitos que empiece con 9"
            )
        return normalized

    @staticmethod
    def _column_name(value) -> str:
        text = unicodedata.normalize("NFKD", str(value).strip().upper())
        return "".join(character for character in text if not unicodedata.combining(character))

    @staticmethod
    def _validation_message(error: Exception) -> str:
        if isinstance(error, ValidationError):
            first = error.errors()[0]
            field = ".".join(str(item) for item in first.get("loc", []))
            return f"{field}: {first.get('msg', 'valor inválido')}"
        return str(error)
