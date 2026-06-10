import pandas as pd

from scripts.import_contacts import read_rows


def test_read_original_excel_columns(tmp_path):
    path = tmp_path / "dataAlumnos.xlsx"
    pd.DataFrame(
        [{"COMPLETO": "Persona de Prueba", "CELULAR": "999999999"}]
    ).to_excel(path, index=False)
    rows = read_rows(path)
    assert rows
    assert "full_name" in rows[0]
    assert "phone_number" in rows[0]
