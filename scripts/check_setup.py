import shutil
import socket
import sys
from pathlib import Path

from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.database.connection import SessionLocal  # noqa: E402


errors = []


def ok(message: str) -> None:
    print(f"[OK] {message}")


def warning(message: str) -> None:
    print(f"[AVISO] {message}")


def error(message: str) -> None:
    errors.append(message)
    print(f"[ERROR] {message}")


def port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main() -> int:
    env_path = ROOT / ".env"
    if env_path.exists():
        ok("Archivo .env encontrado.")
    else:
        error("Falta .env. Copia .env.example como .env y configura DATABASE_URL.")

    if shutil.which("node") and shutil.which("npm"):
        ok("Node.js y npm disponibles.")
    else:
        error("Node.js o npm no están instalados o no están en PATH.")

    bridge_module = ROOT / "bridge" / "node_modules" / "whatsapp-web.js"
    if bridge_module.exists():
        ok("Dependencias del bridge instaladas.")
    else:
        error("Faltan dependencias del bridge. Ejecuta npm install dentro de bridge.")

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        ok("Conexión con PostgreSQL verificada.")
    except Exception:
        error("No se pudo conectar a PostgreSQL. Revisa DATABASE_URL y ejecuta scripts/init_db.py.")

    settings = get_settings()
    try:
        settings.validate_production()
        ok("Configuración de seguridad válida para el entorno.")
    except RuntimeError as validation_error:
        error(str(validation_error))
    if settings.whatsapp_dry_run:
        warning("WHATSAPP_DRY_RUN=true: los envíos serán simulados.")
    else:
        ok("WhatsApp configurado para envíos reales.")

    for port, service in ((8000, "FastAPI"), (3001, "bridge")):
        if port_is_available(port):
            ok(f"Puerto {port} libre para {service}.")
        else:
            warning(f"Puerto {port} en uso. {service} puede estar ejecutándose ya.")

    if errors:
        print(f"\nConfiguración incompleta: {len(errors)} problema(s) por corregir.")
        return 1
    print("\nConfiguración lista para iniciar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
