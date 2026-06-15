from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.services.knowledge_base import KnowledgeBase
from app.services.metrics_service import MetricsService


router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_key(x_admin_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_key
    if expected and x_admin_api_key != expected:
        raise HTTPException(401, "Clave admin inválida")


@router.get("", response_class=HTMLResponse)
def admin_panel():
    return """
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Orientador USIL - Admin</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 2rem; color: #1f2937; }
        section { border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
        code, pre { background: #f4f4f5; padding: .35rem; border-radius: 4px; }
        a { color: #0f766e; }
      </style>
    </head>
    <body>
      <h1>Orientador USIL</h1>
      <section>
        <h2>Métricas</h2>
        <p>JSON: <a href="/admin/metrics">/admin/metrics</a></p>
      </section>
      <section>
        <h2>Conocimiento verificable</h2>
        <p>Consulta las entradas en <a href="/admin/knowledge">/admin/knowledge</a>.</p>
        <p>Para agregar contexto real usa <code>POST /admin/knowledge</code> con
        <code>X-Admin-Api-Key</code> si configuraste <code>ADMIN_API_KEY</code>.</p>
      </section>
      <section>
        <h2>Operación</h2>
        <p>Salud API: <a href="/health">/health</a> · Motor semántico: <a href="/health/llm">/health/llm</a></p>
      </section>
    </body>
    </html>
    """


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    return MetricsService(db).summary()


@router.get("/knowledge")
def knowledge():
    return {"entries": KnowledgeBase().entries}


@router.post("/knowledge", dependencies=[Depends(_require_admin_key)])
def add_knowledge(entry: dict):
    item = KnowledgeBase.add_entry(entry)
    return {"ok": True, "entry": item}
