from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import get_db
from app.services.admin_service import AdminService
from app.services.campaign_service import CampaignService
from app.services.contact_import_service import ContactImportService
from app.services.lead_service import LeadService
from app.services.knowledge_base import KnowledgeBase
from app.services.metrics_service import MetricsService
from app.services.runtime_settings_service import RuntimeSettingsService
from app.schemas.contact_schema import ContactCreate
from app.security import require_admin_key


router = APIRouter(prefix="/admin", tags=["admin"])
ADMIN_INDEX = Path(__file__).resolve().parents[1] / "static" / "admin" / "index.html"


class CampaignRequest(BaseModel):
    campaign_name: str = Field(min_length=3, max_length=120)
    message_template: str = Field(min_length=10, max_length=1200)
    limit: int | None = Field(default=None, ge=1, le=5000)
    delay_seconds: float | None = Field(default=None, ge=1, le=3600)


class CampaignControlRequest(BaseModel):
    action: str = Field(pattern="^(pause|resume|update)$")
    interval_seconds: int | None = Field(default=None, ge=1, le=3600)


class OperationalSettingsUpdate(BaseModel):
    campaign_default_interval_seconds: int | None = Field(default=None, ge=1, le=3600)
    bot_message_debounce_seconds: int | None = Field(default=None, ge=1, le=15)


class ContactUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    opt_out: bool | None = None
    stop_bot: bool | None = None


@router.get("", response_class=FileResponse)
def admin_panel():
    return FileResponse(ADMIN_INDEX)


@router.get("/metrics", dependencies=[Depends(require_admin_key)])
def metrics(db: Session = Depends(get_db)):
    return MetricsService(db).summary()


@router.get("/dashboard", dependencies=[Depends(require_admin_key)])
def dashboard(days: int = Query(default=30, ge=7, le=365), db: Session = Depends(get_db)):
    return AdminService(db).dashboard(days)


@router.get("/campaigns", dependencies=[Depends(require_admin_key)])
def campaigns(limit: int = Query(default=30, ge=1, le=100), db: Session = Depends(get_db)):
    return AdminService(db).campaigns(limit)


@router.post("/campaigns", dependencies=[Depends(require_admin_key)])
def schedule_campaign(payload: CampaignRequest, db: Session = Depends(get_db)):
    return CampaignService(db).schedule(
        campaign_name=payload.campaign_name.strip(),
        message_template=payload.message_template.strip(),
        limit=payload.limit,
        delay_seconds=payload.delay_seconds,
    )


@router.post("/campaigns/{campaign_name}/cancel", dependencies=[Depends(require_admin_key)])
def cancel_campaign(campaign_name: str, db: Session = Depends(get_db)):
    return AdminService(db).cancel_campaign(campaign_name)


@router.patch("/campaigns/{campaign_name}", dependencies=[Depends(require_admin_key)])
def control_campaign(
    campaign_name: str,
    payload: CampaignControlRequest,
    db: Session = Depends(get_db),
):
    return AdminService(db).control_campaign(
        campaign_name,
        payload.action,
        payload.interval_seconds,
    )


@router.get("/queue", dependencies=[Depends(require_admin_key)])
def queue(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return AdminService(db).queue(limit, status)


@router.get("/conversations", dependencies=[Depends(require_admin_key)])
def conversations(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)):
    return AdminService(db).conversations(limit)


@router.get("/contacts", dependencies=[Depends(require_admin_key)])
def contacts(
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return AdminService(db).contacts(limit, search, status)


@router.patch("/contacts/{contact_id}", dependencies=[Depends(require_admin_key)])
def update_contact(contact_id: UUID, payload: ContactUpdate, db: Session = Depends(get_db)):
    values = payload.model_dump(exclude_none=True)
    contact = AdminService(db).update_contact(contact_id, values)
    if not contact:
        raise HTTPException(404, "Contacto no encontrado")
    return contact


@router.post("/contacts/preview", dependencies=[Depends(require_admin_key)])
async def preview_contacts(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "El archivo supera el máximo de 10 MB")
    try:
        return ContactImportService(db).preview(file.filename or "contacts.xlsx", content)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/contacts/import", dependencies=[Depends(require_admin_key)])
def import_previewed_contacts(
    payload: list[ContactCreate],
    db: Session = Depends(get_db),
):
    service = LeadService(db)
    result = {"created": 0, "duplicates": 0, "errors": []}
    for index, item in enumerate(payload, start=1):
        try:
            ContactImportService.normalize_peruvian_phone(item.phone_number)
            _, created = service.create(item)
            result["created" if created else "duplicates"] += 1
        except Exception as error:
            db.rollback()
            result["errors"].append({"row": index, "error": str(error)})
    return result


@router.get("/settings")
def operational_settings(db: Session = Depends(get_db)):
    settings = get_settings()
    return {
        "whatsapp_provider": settings.whatsapp_provider,
        "whatsapp_dry_run": settings.whatsapp_dry_run,
        "campaign_minimum_gap_seconds": settings.campaign_minimum_gap_seconds,
        "rate_limit_messages": settings.rate_limit_messages,
        "rate_limit_window_seconds": settings.rate_limit_window_seconds,
        "admin_key_required": bool(settings.admin_api_key),
        **RuntimeSettingsService(db).all(),
    }


@router.patch("/settings", dependencies=[Depends(require_admin_key)])
def update_operational_settings(
    payload: OperationalSettingsUpdate,
    db: Session = Depends(get_db),
):
    values = payload.model_dump(exclude_none=True)
    return RuntimeSettingsService(db).update(values)


@router.get("/knowledge")
def knowledge():
    return {"entries": KnowledgeBase().entries}


@router.post("/knowledge", dependencies=[Depends(require_admin_key)])
def add_knowledge(entry: dict):
    item = KnowledgeBase.add_entry(entry)
    return {"ok": True, "entry": item}
