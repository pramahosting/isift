"""The Mail page: several mail accounts per person, folders, messages, reply/send and the usual organising actions."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.core import runtime_settings as rs
from app.models import User, AuditLog, IntegrationSetting
from app.integrations import mail as mailer, mailbox as mb
from app.services import calendar_sync as cal
from app.services.invites import EMAIL

async def _commbox_allowed(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    from app.services import entitlements as ent
    await ent.need_commbox(user, db)           # Basic plan: no Commbox unless an administrator allows it

router = APIRouter(prefix="/api/v1/mailbox", tags=["mail"], dependencies=[Depends(_commbox_allowed)])
MAX_ACCOUNTS = 10

def _key(user_id: str) -> str: return f"mailboxes:{user_id}"

async def _stored(db: AsyncSession, user: User) -> list[dict]:
    row = await db.get(IntegrationSetting, _key(user.id))
    items = [dict(a) for a in ((row.value or {}).get("accounts", []) if row else [])]
    legacy = await cal.get_mail(db, user.id)                       # the account added earlier on the Connections page
    if legacy and not any(a["address"] == legacy["address"] for a in items):
        items.insert(0, {"id": "primary", "provider": legacy.get("provider", "other"), "address": legacy["address"], "username": legacy.get("username") or legacy["address"],
                         "smtp_host": legacy["smtp_host"], "smtp_port": legacy["smtp_port"], "imap_host": legacy["imap_host"], "imap_port": legacy["imap_port"],
                         "password": rs._enc(legacy["password"])})
    return items

async def _save(db: AsyncSession, user: User, items: list[dict]):
    row = await db.get(IntegrationSetting, _key(user.id)); val = {"accounts": items}
    if row: row.value = val
    else: db.add(IntegrationSetting(key=_key(user.id), value=val))
    await db.commit()

def _public(a: dict) -> dict:
    d = _public0(a)
    if not a.get("oauth"):    # server settings are not secret; the password never leaves the server
        d["settings"] = {"username": a.get("username") or a["address"], "smtp_host": a.get("smtp_host", ""), "smtp_port": a.get("smtp_port", 587), "imap_host": a.get("imap_host", ""), "imap_port": a.get("imap_port", 993)}
    return d

def _public0(a: dict) -> dict: return {"id": a["id"], "address": a["address"], "provider": a.get("provider", "other"), "label": mailer.PRESETS.get(a.get("provider", "other"), {}).get("label", ""), "oauth": a.get("oauth") or "", "people": a.get("oauth") in ("google", "microsoft")}

async def _account(db: AsyncSession, user: User, aid: str) -> dict:
    a = next((x for x in await _stored(db, user) if x["id"] == aid), None)
    if not a: raise HTTPException(404, "That mail account was not found.")
    a = dict(a); a["password"] = rs._dec(a.get("password", ""))
    if a.get("oauth"):                                   # added with a sign-in popup: use a fresh access token instead of a password
        from app.integrations import oauth
        try: a["access_token"] = await oauth.access_token(a["oauth"], rs._dec(a["refresh_token"]))
        except oauth.OAuthError as exc: raise HTTPException(502, f"{exc} Remove the account and sign in again if this keeps happening.")
    return a

def _wrap(exc: mailer.MailError): return HTTPException(502, str(exc))

@router.get("/accounts")
async def accounts(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    return {"accounts": [_public(a) for a in await _stored(db, user)], "presets": {k: {"label": v["label"], "how": v["how"]} for k, v in mailer.PRESETS.items() if k != "isiftmail"}}

@router.get("/autoconfig")
async def autoconfig(email: str = ""):
    """Server settings for an address, so the Add account form only asks for the password."""
    from app.integrations import mail_autoconfig as ac
    if not EMAIL.match(email.strip().lower()): raise HTTPException(422, "Enter your email address, for example name@example.com.")
    return await ac.detect(email.strip().lower())

@router.post("/accounts")
async def add_account(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    prov = payload.get("provider") if payload.get("provider") in mailer.PRESETS and payload.get("provider") != "isiftmail" else "other"; pre = mailer.PRESETS[prov]
    address = str(payload.get("address") or "").strip().lower(); password = str(payload.get("password") or "")
    if not EMAIL.match(address) or not password: raise HTTPException(422, "Enter your email address and an app password.")
    items = await _stored(db, user)
    if any(a["address"] == address for a in items): raise HTTPException(409, "That account is already added.")
    if len(items) >= MAX_ACCOUNTS: raise HTTPException(422, f"You can add up to {MAX_ACCOUNTS} accounts.")
    try:
        acct = {"provider": prov, "address": address, "username": str(payload.get("username") or address).strip(), "password": password,
                "smtp_host": str(payload.get("smtp_host") or pre["smtp"][0]).strip(), "smtp_port": int(payload.get("smtp_port") or pre["smtp"][1]),
                "imap_host": str(payload.get("imap_host") or pre["imap"][0]).strip(), "imap_port": int(payload.get("imap_port") or pre["imap"][1])}
    except (TypeError, ValueError): raise HTTPException(422, "The port must be a number.")
    try: await mailer.test(acct)
    except mailer.MailError as exc: raise HTTPException(422, str(exc))
    stored = {k: v for k, v in acct.items() if k != "password"}; stored["id"] = uuid.uuid4().hex[:10]; stored["password"] = rs._enc(password)
    items.append(stored); await _save(db, user, items)
    db.add(AuditLog(actor=user.email, action="mailbox.add", resource_type="mail", safe_metadata={"provider": prov})); await db.commit()
    return {"account": _public(stored), "message": f"{address} added."}

@router.patch("/accounts/{aid}")
async def edit_account(aid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Change the password or server settings of an account added with a password. A blank password keeps the saved one."""
    items = await _stored(db, user); a = next((x for x in items if x["id"] == aid), None)
    if not a: raise HTTPException(404, "That mail account was not found.")
    if a.get("oauth"): raise HTTPException(422, "This account uses a sign-in window. Remove it and add it again to change it.")
    if a.get("provider") == "isiftmail": raise HTTPException(422, "An isiftmail address is managed by iSift. Use its Settings (the gear) to change it.")
    prov = payload.get("provider") if payload.get("provider") in mailer.PRESETS and payload.get("provider") != "isiftmail" else a.get("provider", "other"); pre = mailer.PRESETS[prov]
    try:
        new = dict(a); new.update(provider=prov, username=str(payload.get("username") or a.get("username") or a["address"]).strip(),
            smtp_host=str(payload.get("smtp_host") or pre["smtp"][0]).strip(), smtp_port=int(payload.get("smtp_port") or pre["smtp"][1]),
            imap_host=str(payload.get("imap_host") or pre["imap"][0]).strip(), imap_port=int(payload.get("imap_port") or pre["imap"][1]))
    except (TypeError, ValueError): raise HTTPException(422, "The port must be a number.")
    password = str(payload.get("password") or "") or rs._dec(a.get("password", ""))
    test = dict(new); test["password"] = password
    try: await mailer.test(test)
    except mailer.MailError as exc: raise HTTPException(422, str(exc))
    new["password"] = rs._enc(password)
    await _save(db, user, [new if x["id"] == aid else x for x in items])
    if aid == "primary":                       # keep the older single-mailbox record (used for invitation emails) in step
        legacy = await cal.get_mail(db, user.id)
        if legacy:
            legacy.update({k: new[k] for k in ("provider", "username", "smtp_host", "smtp_port", "imap_host", "imap_port")}); legacy["password"] = new["password"]
            await cal.save_mail(db, user.id, legacy)
    db.add(AuditLog(actor=user.email, action="mailbox.edit", resource_type="mail", safe_metadata={"provider": prov})); await db.commit()
    return {"account": _public(new), "message": f"{a['address']} updated."}

@router.delete("/accounts/{aid}")
async def remove_account(aid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    items = await _stored(db, user); a = next((x for x in items if x["id"] == aid), None)
    if not a: raise HTTPException(404, "That mail account was not found.")
    if a.get("provider") == "isiftmail": raise HTTPException(422, "To close your isiftmail address, open its Settings (the gear) and choose Close this mailbox.")
    if aid == "primary": await cal.save_mail(db, user.id, None)
    await _save(db, user, [x for x in items if x["id"] != aid and x["address"] != a["address"]])
    return {"ok": True}

@router.get("/accounts/{aid}/folders")
async def folders(aid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    a = await _account(db, user, aid)
    try: return {"folders": await mb.folders(a)}
    except mailer.MailError as exc: raise _wrap(exc)

@router.get("/accounts/{aid}/messages")
async def messages(aid: str, folder: str = "INBOX", q: str = "", before: int = 0, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    a = await _account(db, user, aid)
    try: return await mb.messages(a, folder, q[:100], 40, before)
    except mailer.MailError as exc: raise _wrap(exc)

@router.get("/accounts/{aid}/message")
async def one_message(aid: str, uid: int, folder: str = "INBOX", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    a = await _account(db, user, aid)
    try: return await mb.message(a, folder, uid)
    except mailer.MailError as exc: raise _wrap(exc)

@router.post("/accounts/{aid}/action")
async def action(aid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    a = await _account(db, user, aid)
    uids = [u for u in (payload.get("uids") or []) if isinstance(u, int)]
    if not uids: raise HTTPException(422, "Select a message first.")
    try: return await mb.act(a, str(payload.get("folder") or "INBOX"), uids, str(payload.get("action") or ""), str(payload.get("target") or ""))
    except mailer.MailError as exc: raise _wrap(exc)

def _addrs(v) -> list[str]:
    items = [x.strip() for x in str(v or "").replace(";", ",").split(",") if x.strip()]
    for x in items:
        from email.utils import parseaddr
        if not EMAIL.match(parseaddr(x)[1].lower()): raise HTTPException(422, f"“{x}” does not look like an email address.")
    return [__import__("email.utils", fromlist=["parseaddr"]).parseaddr(x)[1] for x in items][:50]

@router.post("/accounts/{aid}/send")
async def send(aid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    a = await _account(db, user, aid)
    to = _addrs(payload.get("to")); cc = _addrs(payload.get("cc"))
    if not to: raise HTTPException(422, "Add at least one recipient.")
    subject = str(payload.get("subject") or "").strip()[:300] or "(no subject)"; body = str(payload.get("body") or "")[:200_000]
    mine = a.get("provider") == "isiftmail"
    if mine:
        from app.services import isiftmail_abuse as abuse
        await abuse.check_send(db, a["address"], len(to) + len(cc))
    try: await mb.send(a, to, cc, subject, body, str(payload.get("in_reply_to") or "")[:300])
    except mailer.MailError as exc: raise _wrap(exc)
    if mine: await abuse.record_send(db, a["address"])
    db.add(AuditLog(actor=user.email, action="mailbox.send", resource_type="mail", safe_metadata={"to": len(to)})); await db.commit()
    return {"ok": True, "message": "Message sent."}
