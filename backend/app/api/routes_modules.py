"""Which parts of the app are switched on. Administrators tick modules in Admin Console; unticked modules disappear from the app and the landing page."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import require_admin
from app.models import User, AuditLog, IntegrationSetting

router = APIRouter(prefix="/api/v1", tags=["modules"])
KEY = "modules_disabled"
MODULES = [
    ("meetings", "Meetings", "Meeting list, hosting and joining video meetings, and scheduling a meeting."),
    ("transcripts", "Transcripts", "Read and fetch what was said in a meeting."),
    ("minutes", "Minutes", "AI-written meeting minutes, reviewed by a person."),
    ("actions", "Action items", "Owners, due dates and status for follow-ups."),
    ("briefings", "Briefings", "The morning briefing."),
    ("scheduling", "Booking", "Booking pages and the Share booking link button."),
    ("mail", "Commbox: Mail", "Read and send mail from your accounts."),
    ("isiftmail", "Commbox: isiftmail", "Email addresses for anyone (name@isiftmail), or on your own domain with mailboxes for your team, with signature, auto-reply and drafts. Needs the mail server set up first."),
    ("calendar", "Commbox: Calendar", "The combined calendar."),
    ("contacts", "Commbox: Contacts", "People and groups."),
    ("chat", "Chat", "Messages with people and groups."),
    ("docs", "Notes, WordPerfect, SpreadTable and PowerPresentation", "Notes, agendas and drafts."),
    ("whiteboard", "Whiteboard", "Boards for sketching ideas."),
    ("connections", "Connections", "Link calendars, Zoom and recordings."),
    ("mockdata", "Load mock data", "The Load mock data button on the Dashboard and the Data import page (sample data and CSV import)."),
]
IDS = {m[0] for m in MODULES}

async def disabled(db: AsyncSession) -> list[str]:
    row = await db.get(IntegrationSetting, KEY)
    return [i for i in ((row.value or {}).get("disabled", []) if row else []) if i in IDS]

def _view(off: list[str]): return [{"id": i, "label": l, "description": d, "enabled": i not in off} for i, l, d in MODULES]

@router.get("/modules")
async def modules(db: AsyncSession = Depends(get_db)):
    """Public (the landing page needs it before sign-in). Only says what is on or off."""
    return {"modules": _view(await disabled(db))}

@router.put("/admin/modules")
async def set_modules(payload: dict, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    on = payload.get("enabled") or {}
    off = [i for i, _l, _d in MODULES if on.get(i) is False]
    row = await db.get(IntegrationSetting, KEY)
    if row: row.value = {"disabled": off}
    else: db.add(IntegrationSetting(key=KEY, value={"disabled": off}))
    db.add(AuditLog(actor=user.email, action="modules.set", resource_type="settings", safe_metadata={"disabled": off})); await db.commit()
    return {"modules": _view(off)}
