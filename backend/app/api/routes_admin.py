"""User administration, mock data loading and CSV import."""
import asyncio
import csv, io, logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal, require_admin, hash_password
from app.models import User, LocalAccount, Meeting, Transcript, TranscriptSegment, Minutes, ActionItem, Briefing, AuditLog
from app.services import datasets as ds

from app.services import virtual_room as vrm
from app.services import entitlements as ent
from app.services import billing
router = APIRouter(prefix="/api/v1")
log = logging.getLogger("isift")
BUILTIN_ADMIN = "admin@isift.au"

async def mock_guard(db: AsyncSession = Depends(get_db)):
    from app.api.routes_modules import disabled
    if not settings.mock_data_enabled or "mockdata" in await disabled(db):
        raise HTTPException(403, "Mock data is switched off. An administrator can turn it on in Admin settings (the setting, and Modules).")

@router.get("/features")
async def features(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    from app.api.routes_modules import disabled
    return {"mock_data": bool(settings.mock_data_enabled) and "mockdata" not in await disabled(db), "user_management": bool(settings.is_local_demo), "local_demo": bool(settings.is_local_demo)}

# ---------------- mock data and CSV ----------------
@router.get("/data/tables")
async def data_tables(user: User = Depends(principal), _=Depends(mock_guard)):
    return [{"table": t, "admin_only": s["admin"], "columns": s["columns"], "required": s["required"], "description": s["desc"], "allowed": (not s["admin"]) or user.role == "admin"} for t, s in ds.TABLES.items()]

@router.get("/data/template/{table}", response_class=PlainTextResponse)
async def data_template(table: str, user: User = Depends(principal), _=Depends(mock_guard)):
    if table not in ds.TABLES: raise HTTPException(404, "Unknown table")
    return PlainTextResponse(ds.template_csv(table), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{table}_template.csv"'})

_mock_lock = asyncio.Lock()

@router.post("/data/mock/load")
async def mock_load(reset: bool = False, user: User = Depends(principal), db: AsyncSession = Depends(get_db), _=Depends(mock_guard)):
    try:
        async with _mock_lock:  # one load at a time so repeated clicks cannot collide
            result = await ds.load_mock(db, user, reset)
    except ds.ImportError_ as exc: raise HTTPException(400, str(exc))
    db.add(AuditLog(actor=user.email, action="mock.load", resource_type="dataset", safe_metadata={"reset": reset, "tables": list(result)})); await db.commit()
    return {"message": ds.summarize(result), "tables": result}

@router.post("/data/import/{table}")
async def data_import(table: str, file: UploadFile = File(...), user: User = Depends(principal), db: AsyncSession = Depends(get_db), _=Depends(mock_guard)):
    if table not in ds.TABLES: raise HTTPException(404, "Unknown table")
    if ds.TABLES[table]["admin"] and user.role != "admin": raise HTTPException(403, f"Only an administrator can import {table}.")
    data = await file.read(ds.MAX_BYTES + 1)
    try:
        rows = ds.read_csv(data, table)
        result = await ds.import_rows(db, table, rows, user, await ds.user_tz(db))
    except ds.ImportError_ as exc: raise HTTPException(400, str(exc))
    db.add(AuditLog(actor=user.email, action="csv.import", resource_type=table, safe_metadata={"inserted": result["inserted"], "skipped": result["skipped"], "errors": len(result["errors"])})); await db.commit()
    return {"message": ds.summarize({table: result}), "tables": {table: result}}

# ---------------- users ----------------
class UserCreate(BaseModel):
    email: str
    display_name: str = ""
    password: str = Field(min_length=8, max_length=128)
    role: str = "user"
    is_active: bool = True

class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    virtual_room: bool | None = None
    limits: dict | None = None            # per-person changes: open_room, recording, meeting_minutes, docs_per_day, pdf_pages (null = plan default; 0 = no limit)

async def _account(db, u: User):
    return (await db.execute(select(LocalAccount).where((LocalAccount.id == u.entra_subject) | (LocalAccount.email == u.email)))).scalars().first()

async def _row(db, u: User, counts: dict) -> dict:
    acct = await _account(db, u) if settings.is_local_demo else None
    builtin = settings.is_local_demo and u.email == BUILTIN_ADMIN
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role, "is_active": u.is_active is not False,
            "last_login_at": u.last_login_at, "created_at": u.created_at, "source": "local" if (acct or builtin) else "microsoft",
            "builtin": builtin, "has_password": bool(acct), "meetings": counts.get(u.id, 0), "virtual_room": await vrm.account_on(db, u.email),
            "limits": await ent.summary(db, u), "plan_info": await billing.admin_summary(db, u)}

async def _admins_left(db, excluding: str | None = None) -> int:
    q = select(func.count()).select_from(User).where(User.role == "admin", User.is_active.isnot(False))
    if excluding: q = q.where(User.id != excluding)
    return (await db.execute(q)).scalar_one()

@router.get("/admin/users")
async def list_users(q: str = Query("", max_length=100), admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(User).order_by(User.email)
    if q.strip(): stmt = stmt.where(func.lower(User.email).contains(q.strip().lower()) | func.lower(User.display_name).contains(q.strip().lower()))
    users = (await db.execute(stmt.limit(1000))).scalars().all()
    counts = dict((await db.execute(select(Meeting.owner_id, func.count()).group_by(Meeting.owner_id))).all())
    return [await _row(db, u, counts) for u in users]

@router.post("/admin/users", status_code=201)
async def create_user(data: UserCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if not settings.is_local_demo: raise HTTPException(400, "Users sign in with Microsoft in this mode. Invite them in Microsoft Entra; they appear here after their first sign-in, and you can set their role here.")
    try: u = await ds.create_local_user(db, data.email, data.display_name, data.password, data.role, data.is_active)
    except ValueError as exc: raise HTTPException(409 if "exists" in str(exc) else 422, str(exc))
    db.add(AuditLog(actor=admin.email, action="user.create", resource_type="user", resource_id=u.id, safe_metadata={"role": u.role}))
    await db.commit(); await db.refresh(u)
    return await _row(db, u, {})

async def _get(db, user_id: str) -> User:
    u = await db.get(User, user_id)
    if not u: raise HTTPException(404, "User not found")
    return u

@router.patch("/admin/users/{user_id}")
async def update_user(user_id: str, data: UserPatch, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get(db, user_id); builtin = settings.is_local_demo and u.email == BUILTIN_ADMIN
    changed = []
    if data.role is not None and data.role != u.role:
        if data.role not in ("admin", "user"): raise HTTPException(422, "Role must be admin or user.")
        if builtin: raise HTTPException(409, "The built-in administrator always keeps the admin role.")
        if u.id == admin.id: raise HTTPException(409, "You cannot change your own role.")
        if data.role == "user" and u.role == "admin" and await _admins_left(db, u.id) == 0: raise HTTPException(409, "There must be at least one active administrator.")
        u.role = data.role; u.role_override = data.role; changed.append("role")
    if data.is_active is not None and data.is_active != (u.is_active is not False):
        if not data.is_active:
            if builtin: raise HTTPException(409, "The built-in administrator cannot be disabled.")
            if u.id == admin.id: raise HTTPException(409, "You cannot disable your own account.")
            if u.role == "admin" and await _admins_left(db, u.id) == 0: raise HTTPException(409, "There must be at least one active administrator.")
        u.is_active = data.is_active; changed.append("active")
    if data.display_name is not None and data.display_name.strip() and data.display_name != u.display_name:
        u.display_name = data.display_name.strip(); changed.append("name")
        acct = await _account(db, u)
        if acct: acct.display_name = u.display_name
    if data.password is not None:
        if builtin: raise HTTPException(409, "The built-in administrator password is set by the system.")
        acct = await _account(db, u)
        if not acct: raise HTTPException(400, "This user signs in with Microsoft; there is no password to change.")
        acct.password_hash = hash_password(data.password); changed.append("password")
    if data.virtual_room is not None and data.virtual_room != await vrm.account_on(db, u.email):
        await vrm.set_account(db, u.email, data.virtual_room); changed.append("virtual_room")
    if data.limits is not None:
        bad = [k for k, v in data.limits.items() if k not in ent.FIELDS or (v is not None and not isinstance(v, (bool, int)))]
        if bad: raise HTTPException(422, "Unknown limit: " + ", ".join(bad))
        await ent.set_overrides(db, u.email, data.limits); changed.append("limits")
    if changed: db.add(AuditLog(actor=admin.email, action="user.update", resource_type="user", resource_id=u.id, safe_metadata={"fields": changed}))
    await db.commit(); await db.refresh(u)
    return await _row(db, u, {})

async def _drop(db, key: str) -> None:           # like store.drop, but the caller commits, so the whole deletion is one step
    from app.models import IntegrationSetting
    row = await db.get(IntegrationSetting, key)
    if row: await db.delete(row)

async def _forget(db, u: User) -> None:
    """Remove what is stored about a person outside their rows: profile and limits, plan record, usage counters, and their place in a company."""
    from app.services import store
    em = (u.email or "").strip().lower()
    link = await store.get(db, store.hkey("memberof", em), {})
    cid = link.get("company_id")
    if cid:
        c = await store.get(db, f"company:{cid}", {})
        if c:
            c["members"] = [m for m in c.get("members", []) if (m.get("email") or "").lower() != em]
            if c["members"]:
                if not any(m.get("role") == "owner" for m in c["members"]): c["members"][0]["role"] = "owner"      # the company always keeps an owner
                await store.put(db, f"company:{cid}", c, commit=False)
            else:
                await _drop(db, f"company:{cid}"); await _drop(db, f"billing:co:{cid}")
    for prefix in ("profile", "billing", "memberof", "docs-usage", "ai-usage", "meet-usage", "pendingsignup"):
        await _drop(db, store.hkey(prefix, em))

@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    u = await _get(db, user_id)
    if settings.is_local_demo and u.email == BUILTIN_ADMIN: raise HTTPException(409, "The built-in administrator cannot be deleted.")
    if u.id == admin.id: raise HTTPException(409, "You cannot delete your own account.")
    if u.role == "admin" and await _admins_left(db, u.id) == 0: raise HTTPException(409, "There must be at least one active administrator.")
    ids = [x for (x,) in (await db.execute(select(Meeting.id).where(Meeting.owner_id == u.id))).all()]
    if ids:
        tids = [x for (x,) in (await db.execute(select(Transcript.id).where(Transcript.meeting_id.in_(ids)))).all()]
        if tids: await db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id.in_(tids)))
        await db.execute(delete(Transcript).where(Transcript.meeting_id.in_(ids)))
        await db.execute(delete(Minutes).where(Minutes.meeting_id.in_(ids)))
        await db.execute(delete(ActionItem).where(ActionItem.meeting_id.in_(ids)))
        await db.execute(delete(Meeting).where(Meeting.id.in_(ids)))
    await db.execute(delete(Briefing).where(Briefing.user_id == u.id))
    acct = await _account(db, u) if settings.is_local_demo else None
    if acct: await db.delete(acct)
    email = u.email
    await _forget(db, u)                                  # per-person records kept outside the user table
    await db.delete(u)
    db.add(AuditLog(actor=admin.email, action="user.delete", resource_type="user", resource_id=user_id, safe_metadata={"email_domain": email.split("@")[-1], "meetings_removed": len(ids)}))
    await db.commit()
    return {"deleted": True, "meetings_removed": len(ids)}

@router.get("/admin/users/export", response_class=PlainTextResponse)
async def export_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    out = io.StringIO(); w = csv.writer(out); w.writerow(["email", "display_name", "role", "password", "is_active"])
    for u in (await db.execute(select(User).order_by(User.email))).scalars():
        w.writerow([u.email, u.display_name, u.role, "", "true" if u.is_active is not False else "false"])
    return PlainTextResponse(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="users.csv"'})


@router.get("/admin/setup-status")
async def setup_status(user: User = Depends(require_admin)):
    """Plain checklist of what is and is not configured, for the Admin settings page."""
    from app.services.llm import ai_configured, transcription_configured
    from app.services.calendar_sync import graph_configured
    from app.integrations import zoom
    ice = [u for u in (settings.ice_servers or "").split(",") if u.strip()]
    has_turn = any(u.strip().lower().startswith(("turn:", "turns:")) for u in ice) or bool(settings.cf_turn_key_id and settings.cf_turn_api_token)
    default_pw = settings.local_admin_password == "Meeting$1" if settings.is_local_demo else False
    items = [
        {"key": "password", "title": "Administrator password", "required": True, "ok": not default_pw,
         "detail": "Still the built-in sample password. Set LOCAL_ADMIN_PASSWORD in the .env file, then restart." if default_pw else "Changed from the sample password."},
        {"key": "ai", "title": "AI for minutes and briefings (Groq)", "required": True, "ok": ai_configured(),
         "detail": "Add the Groq API key and model under Admin settings > Groq AI." if not ai_configured() else "Ready."},
        {"key": "transcription", "title": "Speech-to-text for recordings", "required": False, "ok": transcription_configured(),
         "detail": "Needs the Groq key. Recordings up to 25 MB are transcribed with Groq Whisper." if not transcription_configured() else "Ready."},
        {"key": "calendar", "title": "Calendar source", "required": False, "ok": bool(graph_configured() or settings.machine_calendar_allowed),
         "detail": "Each person adds their calendar under Connections (links, CalDAV, .ics), or enable Microsoft 365 / this computer's calendar."},
        {"key": "zoom", "title": "Zoom (create Zoom meetings, fetch recordings)", "required": False, "ok": zoom.configured(),
         "detail": "Optional. Add the Server-to-Server OAuth app under Admin settings > Zoom." if not zoom.configured() else "Ready."},
        {"key": "turn", "title": "TURN relay for video meetings", "required": False, "ok": has_turn,
         "detail": "Strongly recommended. Without a relay, video and sound do not reach people on company networks, phone data or some home routers, and calls get slow. Easiest: paste a Cloudflare TURN key ID and token under Video meetings." if not has_turn else "Ready."},
        {"key": "https", "title": "Secure address for camera and microphone", "required": False,
         "ok": bool(settings.frontend_origin.startswith("https://") or "localhost" in settings.frontend_origin or "127.0.0.1" in settings.frontend_origin),
         "detail": "Other computers need https to use camera/microphone. Set MI_LISTEN=lan (or MI_HTTPS=true) in .env."},
        {"key": "mail", "title": "Email sent by the app (sign-up codes)", "required": False, "ok": bool((settings.smtp_host and settings.error_email_to) or (settings.resend_api_key and settings.smtp_from)),
         "detail": "Needed for sign-up verification codes, booking emails and alerts. If codes never arrive, your host probably blocks SMTP: use a Resend API key instead (Admin settings > Email sent by the app). Then press Send test email."},
    ]
    return {"items": items, "ready": all(i["ok"] for i in items if i["required"])}


@router.post("/admin/email/test")
async def email_test(payload: dict, user: User = Depends(require_admin)):
    """Send a real test message from the app's email account and report exactly what the mail server said."""
    from app.services import signup as su
    from app.integrations import mail
    to = str(payload.get("to") or "").strip().lower()
    if not su.EMAIL.fullmatch(to): raise HTTPException(422, "Enter the address to send the test to.")
    acct = su.app_sender()
    if not acct: raise HTTPException(409, "No email account is set up yet. Fill in SMTP host and From address (and the user name and password your mail provider needs), save, then try again.")
    try: await mail.send(acct, [to], "iSift test email", "This is a test from iSift. Sign-up codes, booking confirmations and failure alerts will be sent from this account.")
    except Exception as exc: raise HTTPException(502, "The mail server did not accept the message: " + str(exc)[:240])
    return {"message": f"Test email sent to {to} from {acct['from']}. Check the inbox and the spam folder."}
