import io

import pandas as pd

from app.services.contact_import_service import ContactImportService


class FakeDb:
    def __init__(self, existing=()):
        self.existing = existing

    def scalars(self, query):
        return iter(self.existing)


def excel_bytes(rows):
    stream = io.BytesIO()
    pd.DataFrame(rows).to_excel(stream, index=False)
    return stream.getvalue()


def test_preview_maps_excel_columns_and_normalizes_phone():
    content = excel_bytes([
        {
            "COMPLETO": "Ana Perez",
            "CELULAR": "987 654 321",
            "COLEGIO": "Colegio Uno",
            "CORREO": "ana@example.com",
            "CARRERA": "Derecho",
        }
    ])

    result = ContactImportService(FakeDb()).preview("alumnos.xlsx", content)

    assert result["summary"] == {
        "total": 1,
        "valid": 1,
        "invalid": 0,
        "duplicates": 0,
    }
    assert result["rows"][0]["data"]["phone_number"] == "51987654321"
    assert result["rows"][0]["data"]["full_name"] == "Ana Perez"


def test_preview_marks_bad_phone_and_duplicates():
    content = excel_bytes([
        {"COMPLETO": "Número corto", "CELULAR": "99999999"},
        {"COMPLETO": "Duplicado", "CELULAR": "987654321"},
    ])

    result = ContactImportService(FakeDb(existing=("51987654321",))).preview(
        "alumnos.xlsx", content
    )

    assert result["summary"]["invalid"] == 1
    assert result["summary"]["duplicates"] == 1
    assert result["rows"][0]["status"] == "invalid"
    assert result["rows"][1]["status"] == "duplicate"


def test_preview_requires_phone_column():
    content = excel_bytes([{"COMPLETO": "Ana"}])

    try:
        ContactImportService(FakeDb()).preview("alumnos.xlsx", content)
    except ValueError as error:
        assert "CELULAR" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError")
