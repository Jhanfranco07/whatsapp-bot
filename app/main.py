import logging
import inspect
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.config import get_settings
from app.database.repositories import ContactRepository, MessageRepository
from app.routers.admin import router as admin_router
from app.schemas.contact_schema import ContactCreate, ContactRead
from app.schemas.message_schema import MessageRead
from app.schemas.webhook_schema import InboundMessage, InboundResponse
from app.services.campaign_service import CampaignService
from app.services.conversation_service import ConversationService
from app.services.lead_service import LeadService
from app.services.outbound_queue_service import OutboundQueueService
from app.services.semantic_engine import get_semantic_engine
from app.utils.logger import configure_logging


configure_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Construye el índice TF-IDF una sola vez al iniciar FastAPI."""
    get_semantic_engine()
    yield


app = FastAPI(title="Orientador USIL", version="1.0.0", lifespan=lifespan)
app.include_router(admin_router)


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "orientador-usil",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True, "service": "orientador-usil", "database": "connected"}
    except SQLAlchemyError as error:
        logger.exception("PostgreSQL no disponible")
        raise HTTPException(503, "database unavailable") from error


@app.get("/health/llm")
def llm_health():
    engine = get_semantic_engine()
    probe = engine.classify("hola")
    if engine.intents_loaded < 8 or probe.intent != "saludo" or probe.confidence <= 0.5:
        raise HTTPException(503, "semantic engine unavailable")
    return {
        "status": "ok",
        "engine": "tfidf_semantic",
        "intents_loaded": engine.intents_loaded,
        "probe": {
            "text": "hola",
            "intent": probe.intent,
            "confidence": probe.confidence,
        },
    }


@app.post("/webhooks/whatsapp/inbound", response_model=InboundResponse)
@app.post("/simulate/inbound", response_model=InboundResponse)
async def inbound(
    payload: InboundMessage,
    request: Request,
    db: Session = Depends(get_db),
    x_inbound_api_key: str | None = Header(default=None),
):
    is_webhook = request.url.path == "/webhooks/whatsapp/inbound"
    if is_webhook and settings.inbound_api_key and x_inbound_api_key != settings.inbound_api_key:
        raise HTTPException(401, "Clave inbound inválida")
    try:
        service = ConversationService(db)
        handler = getattr(service, "process_inbound_async", service.process_inbound)
        result = handler(payload)
        return await result if inspect.isawaitable(result) else result
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("Error procesando inbound")
        raise HTTPException(503, "No se pudo guardar la conversación") from error


@app.post("/campaigns/send")
def send_campaign(
    limit: int | None = Query(default=None, ge=1),
    phone_number: str | None = Query(default=None),
    delay_seconds: float = Query(default=60, ge=1, le=3600),
    db: Session = Depends(get_db),
):
    return CampaignService(db).send_initial(limit, phone_number, delay_seconds)


@app.post("/outbound/dispatch")
def dispatch_outbound(
    limit: int = Query(default=1, ge=1, le=20),
    db: Session = Depends(get_db),
    x_admin_api_key: str | None = Header(default=None),
):
    if settings.admin_api_key and x_admin_api_key != settings.admin_api_key:
        raise HTTPException(401, "Clave admin inválida")
    return OutboundQueueService(db).dispatch_pending(limit)


@app.get("/contacts", response_model=list[ContactRead])
def list_contacts(db: Session = Depends(get_db)):
    return ContactRepository(db).list()


@app.post("/contacts", response_model=ContactRead, status_code=201)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db)):
    try:
        contact, created = LeadService(db).create(payload)
        if not created:
            raise HTTPException(409, "El teléfono ya está registrado")
        return contact
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "El teléfono ya está registrado") from error


@app.post("/contacts/import")
def import_contacts(payload: list[ContactCreate], db: Session = Depends(get_db)):
    service = LeadService(db)
    result = {"created": 0, "duplicates": 0, "errors": []}
    for index, item in enumerate(payload, start=1):
        try:
            _, created = service.create(item)
            result["created" if created else "duplicates"] += 1
        except (ValueError, IntegrityError) as error:
            db.rollback()
            result["errors"].append({"row": index, "error": str(error)})
    return result


@app.get("/contacts/{phone_number}/messages", response_model=list[MessageRead])
def contact_messages(phone_number: str, db: Session = Depends(get_db)):
    contact = ContactRepository(db).get_by_phone(phone_number)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    return MessageRepository(db).history(contact.id)
