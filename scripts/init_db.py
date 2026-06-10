import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.init_db import init_db


if __name__ == "__main__":
    try:
        init_db()
        print("Conexión verificada y tablas PostgreSQL inicializadas.")
    except Exception as error:
        print(
            "No se pudo conectar a PostgreSQL. Revisa DATABASE_URL en .env "
            "y confirma que la base orientador_usil exista."
        )
        raise SystemExit(1) from error
