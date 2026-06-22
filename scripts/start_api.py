import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from app.config import get_settings


HOST = "127.0.0.1"
PORT = 8000


def api_is_running() -> bool:
    try:
        with urlopen(f"http://{HOST}:{PORT}/health", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and payload.get("ok") is True
    except (OSError, URLError, ValueError):
        return False


def main() -> int:
    if api_is_running():
        print(f"FastAPI ya está ejecutándose en http://{HOST}:{PORT}.")
        print("No es necesario abrir otra instancia.")
        return 0
    settings = get_settings()
    print(f"Iniciando FastAPI en http://{HOST}:{PORT}...")
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
