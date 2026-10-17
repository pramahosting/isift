"""Sign-in popups for adding a Google, Microsoft or Yahoo mailbox (like Outlook's 'Add account')."""
import html, json, uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.core import runtime_settings as rs
from app.models import User, AuditLog, IntegrationSetting
from app.integrations import oauth
from app.integrations.graph import GraphUnavailable
from app.api import routes_mailbox as mbx
from app.api.routes_workspace import import_contacts
from app.services import calendar_sync as cal

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])

@router.get("/providers")
async def providers(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await rs.apply_overrides(db)
    return {"providers": [{"id": k, "label": v["label"], "ready": oauth.ready(k), "people": v["people"]} for k, v in oauth.PROVIDERS.items()]}

@router.get("/detect")
async def detect(email: str = "", user: User = Depends(principal)):
    """Which sign-in an email address uses (like Outlook's first screen). provider is null when the domain is not recognised."""
    return {"provider": oauth.detect(email)}

@router.post("/{provider}/start")
async def start(provider: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    if provider not in oauth.PROVIDERS: raise HTTPException(404, "Unknown provider.")
    await rs.apply_overrides(db)
    if not oauth.ready(provider): raise HTTPException(409, f"{oauth.PROVIDERS[provider]['label']} sign-in is not set up yet.")
    o = urlsplit(str(payload.get("origin") or ""))
    if o.scheme not in ("http", "https") or not o.netloc: raise HTTPException(422, "Missing page address.")
    origin = f"{o.scheme}://{o.netloc}"; redirect = origin + "/api/v1/oauth/callback"
    hint = str(payload.get("email") or "").strip()[:320]
    verifier, challenge = oauth.pkce(); state = uuid.uuid4().hex + uuid.uuid4().hex
    db.add(IntegrationSetting(key=f"oauth_state:{state}", value={"provider": provider, "user_id": user.id, "verifier": verifier, "redirect": redirect, "origin": origin, "at": datetime.now(timezone.utc).isoformat()}))
    await db.commit()
    return {"url": oauth.auth_url(provider, redirect, state, challenge, hint), "redirect_uri": redirect}

def _page(origin: str, ok: bool, message: str, account_id: str = "") -> HTMLResponse:
    data = json.dumps({"type": "isift-oauth", "ok": ok, "message": message, "accountId": account_id}).replace("<", "\\u003c")
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><title>iSift</title><body style="font:16px system-ui;padding:32px;max-width:520px;margin:auto">
<h2>{'Account added' if ok else 'Sign-in did not finish'}</h2><p>{html.escape(message)}</p><p>You can close this window.</p>
<script>try{{window.opener&&window.opener.postMessage({data},{json.dumps(origin)})}}catch(e){{}};setTimeout(function(){{window.close()}},{900 if ok else 2500})</script>""")

async def pull_people(db: AsyncSession, user: User, a: dict) -> str:
    """Calendar (next 30 days) and contacts for a Google or Microsoft account. Returns a short note."""
    kind = a.get("oauth"); tz = await cal.user_timezone(db); start, _ = cal.today_window(tz); end = start + timedelta(days=30)
    refresh = rs._dec(a["refresh_token"]); note = ""
    try:
        if kind == "google":
            tok = await oauth.access_token("google", refresh)
            ev = await oauth.google_calendar(tok, start, end); people = await oauth.google_contacts(tok); src = "google"
        elif kind == "microsoft":
            from app.integrations import graph as g
            tok = await oauth.access_token("microsoft", refresh, "graph")
            ev = await g.me_calendar(tok, start, end); people = await g.me_contacts(tok); src = "outlook"
        else: return ""
        r = await cal.apply_events(db, user.id, ev, start, end, src, mark_stale=False, account=a["address"])
        c = await import_contacts(db, user, people, a["address"])
        note = f"{r['eligible']} meetings in the next 30 days and {c['added']} new contacts brought in."
    except (oauth.OAuthError, GraphUnavailable) as exc: note = f"Calendar and contacts could not be read: {exc}"
    return note

@router.get("/callback", response_class=HTMLResponse)
async def callback(request: Request, code: str = "", state: str = "", error: str = "", error_description: str = "", db: AsyncSession = Depends(get_db)):
    row = await db.get(IntegrationSetting, f"oauth_state:{state}") if state else None
    if not row: return _page("null", False, "This sign-in link has expired. Close this window and try again.")
    st = dict(row.value); await db.delete(row); await db.commit()
    origin = st["origin"]
    try: fresh = datetime.now(timezone.utc) - datetime.fromisoformat(st["at"]) < timedelta(minutes=15)
    except Exception: fresh = False
    if not fresh: return _page(origin, False, "This sign-in took too long. Try again.")
    if error or not code: return _page(origin, False, error_description or "Sign-in was cancelled.")
    await rs.apply_overrides(db)
    provider = st["provider"]; p = oauth.PROVIDERS[provider]
    user = await db.get(User, st["user_id"])
    if not user: return _page(origin, False, "Your session was not found.")
    try:
        tokens = await oauth.exchange_code(provider, code, st["redirect"], st["verifier"])
        who = await oauth.whoami(provider, tokens["access_token"])
        refresh = tokens.get("refresh_token")
        if not refresh: raise oauth.OAuthError(f"{p['label']} did not allow continued access. Remove iSift from your {p['label']} account's connected apps and sign in again.")
        if not who["email"]: raise oauth.OAuthError("Could not read the email address of that account.")
    except oauth.OAuthError as exc: return _page(origin, False, str(exc))
    items = await mbx._stored(db, user)
    acct = next((x for x in items if x["address"] == who["email"]), None)
    if not acct:
        if len(items) >= mbx.MAX_ACCOUNTS: return _page(origin, False, f"You can add up to {mbx.MAX_ACCOUNTS} accounts.")
        acct = {"id": uuid.uuid4().hex[:10], "provider": p["mail_provider"], "address": who["email"], "username": who["email"], "smtp_host": p["smtp"][0], "smtp_port": p["smtp"][1],
                "imap_host": p["imap"][0], "imap_port": p["imap"][1]}; items.append(acct)
    acct.update(oauth=provider, refresh_token=rs._enc(refresh)); acct.pop("password", None)
    await mbx._save(db, user, items)
    db.add(AuditLog(actor=user.email, action="mailbox.oauth", resource_type="mail", safe_metadata={"provider": provider})); await db.commit()
    note = await pull_people(db, user, acct) if p["people"] else ""
    return _page(origin, True, f"{who['email']} is added. {note}".strip(), acct["id"])

@router.post("/accounts/{aid}/sync")
async def sync_people(aid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    a = next((x for x in await mbx._stored(db, user) if x["id"] == aid), None)
    if not a or not a.get("oauth"): raise HTTPException(404, "That account does not use a sign-in popup.")
    return {"message": await pull_people(db, user, a) or "Nothing to sync for this account."}
