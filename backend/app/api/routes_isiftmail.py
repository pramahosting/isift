"""isiftmail inside Commbox: an email address (name@isiftmail.com by default) for any signed-in person, or on their own domain (pramod@prama-ai.com) hosted here.

The mailbox is then an ordinary Commbox account (inbox, folders, compose, delete all use the existing Mail routes). This file adds only what is new:
getting a mailbox, bringing and verifying your own domain, drafts, the signature, the auto-reply, a password for other apps, and closing a mailbox.
The module can be switched off in Admin Console (Customers > Modules) and per plan; nothing here is reachable while it is off.
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.core import runtime_settings as rs
from app.models import User, AuditLog, IntegrationSetting
from app.integrations import isiftmail as im, mail as mailer
from app.services.invites import EMAIL
from app.api import routes_mailbox as mbx

MODULE = "isiftmail"
CLOSED_KEY = "isiftmail_closed"
DOMAIN_PREFIX = "isiftmail_dom:"
HOLD_DAYS = 180            # a closed address is not given to someone else for this long, so mail meant for the old owner cannot reach a stranger
MAX_DOMAINS = 3
BOX_PREFIX = "isiftmail_box:"        # one record per mailbox: who runs it (the domain owner) and whose Commbox it appears in
MAX_BOXES_PER_DOMAIN = 50

async def _module_on(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    from app.api.routes_modules import disabled
    from app.services import entitlements as ent
    off = set(await disabled(db)) | set(await ent.modules_off(db, user))
    if MODULE in off or "mail" in off: raise HTTPException(403, "isiftmail is switched off. An administrator can turn it on under Customers > Modules.")

router = APIRouter(prefix="/api/v1/isiftmail", tags=["isiftmail"], dependencies=[Depends(mbx._commbox_allowed), Depends(_module_on)])

def _skey(user_id: str, aid: str) -> str: return f"isiftmail:{user_id}:{aid}"
def _dom_of(a: dict) -> str: return a["address"].rsplit("@", 1)[-1]

async def _mailboxes(db: AsyncSession, user: User) -> list[dict]:
    return [a for a in await mbx._stored(db, user) if a.get("provider") == im.PROVIDER]

async def _mine(db: AsyncSession, user: User, aid: str = "") -> dict | None:
    items = await _mailboxes(db, user)
    return next((a for a in items if a["id"] == aid), None) if aid else (items[0] if items else None)

async def _ready():
    if not im.configured(): raise HTTPException(503, "isiftmail is not set up on this server yet.")

# ---- closed addresses are held back for a while
async def _closed(db: AsyncSession) -> dict:
    row = await db.get(IntegrationSetting, CLOSED_KEY); return dict((row.value or {}).get("names", {})) if row else {}

def _held(closed: dict, address: str) -> bool:
    t = closed.get(address)
    if not t: return False
    try: return datetime.fromisoformat(t) > datetime.now(timezone.utc) - timedelta(days=HOLD_DAYS)
    except ValueError: return False

# ---- a person's own domains
async def _dom_rows(db: AsyncSession, dom: str | None = None) -> list[IntegrationSetting]:
    like = f"{DOMAIN_PREFIX}{dom}:%" if dom else f"{DOMAIN_PREFIX}%"
    return list((await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like(like)))).scalars())

async def _my_domains(db: AsyncSession, user: User) -> list[IntegrationSetting]:
    return [r for r in await _dom_rows(db) if (r.value or {}).get("owner") == user.id]

async def _my_domain(db: AsyncSession, user: User, dom: str) -> IntegrationSetting | None:
    return await db.get(IntegrationSetting, f"{DOMAIN_PREFIX}{dom}:{user.id}")

def _dom_view(r: IntegrationSetting) -> dict:
    v = r.value or {}; dom = v["domain"]
    return {"domain": dom, "status": v.get("status", "pending"), "records": im.dns_records(dom, v.get("token", ""), v.get("server"))}

# ---- the register of mailboxes: lets a domain owner manage the mailboxes of other people (like the Microsoft 365 admin centre)
async def _rec(db: AsyncSession, address: str) -> IntegrationSetting | None: return await db.get(IntegrationSetting, BOX_PREFIX + address)

async def _recs(db: AsyncSession) -> list[IntegrationSetting]:
    return list((await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like(BOX_PREFIX + "%")))).scalars())

async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email.strip().lower()))).scalars().first()

async def _put_in_commbox(db: AsyncSession, who: User, rec: dict) -> bool:
    """Adds the mailbox to this person's Mail. False when they already have the most accounts allowed."""
    items = await mbx._stored(db, who)
    if any(x["address"] == rec["address"] for x in items): return True
    if len(items) >= mbx.MAX_ACCOUNTS: return False
    acct = im.account_dict(rec["login"], rec["password"], rec["address"]); acct["id"] = rec["account_id"]
    await mbx._save(db, who, items + [acct]); return True

async def _claim_waiting(db: AsyncSession, user: User) -> None:
    """Mailboxes a domain owner made for this person's email address appear in their Mail the first time they look."""
    for row in await _recs(db):
        v = row.value or {}
        if v.get("assignee") == user.email.lower() and not v.get("claimed") and await _put_in_commbox(db, user, v):
            row.value = {**v, "claimed": True}; await db.commit()

# ---- who may have the free address on our own domain: everybody, one each (the administrator may have several)
async def _can_default(db: AsyncSession, user: User) -> bool:
    return user.role == "admin" or not any(_dom_of(a) == im.domain() for a in await _mailboxes(db, user))

@router.get("/status")
async def status(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    avail = im.configured()
    if avail: await _claim_waiting(db, user)
    boxes = await _mailboxes(db, user); doms = await _my_domains(db, user)
    room = len(await mbx._stored(db, user)) < mbx.MAX_ACCOUNTS
    free = avail and room and await _can_default(db, user); verified = [r for r in doms if (r.value or {}).get("status") == "verified"]
    return {"available": avail, "domain": im.domain(), "mailboxes": [{"id": a["id"], "address": a["address"], "domain": _dom_of(a)} for a in boxes],
            "mailbox": ({"id": boxes[0]["id"], "address": boxes[0]["address"]} if boxes else None),
            "eligible": bool(free), "can_create": bool(avail and room and (free or verified)),
            "domains": [{"domain": r.value["domain"], "status": r.value.get("status", "pending")} for r in doms],
            "reason": "" if free or not avail else ("You can add an address on your own domain." if verified else "You already have your free address. Add your own domain to make more.")}

async def _target(db: AsyncSession, user: User, dom: str) -> str:
    """Which domain a new address goes on: ours, or one of the person's own that has been proven to be theirs."""
    dom = (dom or im.domain()).strip().lower()
    if dom == im.domain():
        if not await _can_default(db, user): raise HTTPException(409, "You already have your free address. Add your own domain to make more.")
        return dom
    row = await _my_domain(db, user, dom)
    if not row or (row.value or {}).get("status") != "verified": raise HTTPException(403, "That domain is not verified yet. Add it and check its DNS records first.")
    return dom

@router.get("/check")
async def check(name: str, domain: str = "", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _ready()
    dom = await _target(db, user, domain)
    try: n = im.valid_name(name, reserved=dom == im.domain())
    except ValueError as exc: return {"ok": False, "message": str(exc)}
    address = f"{n}@{dom}"
    if _held(await _closed(db), address): return {"ok": False, "name": n, "message": "That address is not available."}
    try: taken = await im.exists(im.principal_name(n, dom))
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    return {"ok": not taken, "name": n, "address": address, "message": "That name is taken. Try another." if taken else "Available."}


_NEW_BY_NET: dict[str, list[float]] = {}
def _net(request: Request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "unknown")

async def _creation_limit(db: AsyncSession, user: User, request: Request):
    """Open sign-up invites bulk sign-ups: limit new addresses per person and per network address per day."""
    import time
    cap = max(1, int(rs.settings.isiftmail_new_per_day or 3))
    cut = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    made = sum(1 for r in await _recs(db) if (r.value or {}).get("owner") == user.id and (r.value or {}).get("created", "") > cut)
    now = time.time(); net = _net(request); hits = [t for t in _NEW_BY_NET.get(net, []) if now - t < 86400]
    if made >= cap or len(hits) >= cap * 3:
        raise HTTPException(429, "You have opened the most new addresses allowed for today. Please try again tomorrow.")
    hits.append(now); _NEW_BY_NET[net] = hits

@router.post("/create")
async def create(payload: dict, request: Request, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _ready()
    dom = await _target(db, user, str(payload.get("domain") or ""))
    if dom == im.domain(): await _creation_limit(db, user, request)      # own domains already have their own cap
    try: n = im.valid_name(payload.get("name"), reserved=dom == im.domain())
    except ValueError as exc: raise HTTPException(422, str(exc))
    address = f"{n}@{dom}"
    for_email = str(payload.get("for_email") or "").strip().lower(); other = bool(for_email) and for_email != user.email.lower()
    if other:                                  # a mailbox for somebody else: only on a domain the person owns
        if dom == im.domain(): raise HTTPException(422, "You can only make addresses for other people on your own domain.")
        if not EMAIL.match(for_email): raise HTTPException(422, "Enter that person's email address (the one they use to sign in to iSift).")
        if sum(1 for r in await _recs(db) if (r.value or {}).get("domain") == dom) >= MAX_BOXES_PER_DOMAIN: raise HTTPException(422, f"A domain can have up to {MAX_BOXES_PER_DOMAIN} mailboxes.")
    if _held(await _closed(db), address): raise HTTPException(409, "That address is not available.")
    items = await mbx._stored(db, user)
    if not other and len(items) >= mbx.MAX_ACCOUNTS: raise HTTPException(422, f"You can add up to {mbx.MAX_ACCOUNTS} accounts.")
    login, pw = im.principal_name(n, dom), im.new_password()
    try:
        if await im.exists(login): raise HTTPException(409, "That name is taken. Try another.")
        await im.create(login, pw, str(payload.get("display_name") or "").strip()[:80] or (user.display_name if not other else "") or n, address)
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    rec = {"address": address, "login": login, "domain": dom, "owner": user.id, "assignee": for_email if other else user.email.lower(), "claimed": False,
           "password": rs._enc(pw), "account_id": uuid.uuid4().hex[:10], "display": str(payload.get("display_name") or "").strip()[:80], "created": datetime.now(timezone.utc).isoformat()}
    note = ""
    try:
        if not other: rec["claimed"] = await _put_in_commbox(db, user, rec)
        else:
            who = await _user_by_email(db, for_email)
            if who and await _put_in_commbox(db, who, rec): rec["claimed"] = True; note = f"It now appears in {for_email}'s Mail."
            else: note = f"It will appear in Mail when {for_email} signs in to iSift with that email address."
        db.add(IntegrationSetting(key=BOX_PREFIX + address, value=rec)); await db.commit()
    except Exception:
        try: await im.remove(login)
        except Exception: pass
        raise
    db.add(AuditLog(actor=user.email, action="isiftmail.create", resource_type="mail", safe_metadata={"address": address, "for_other": other})); await db.commit()
    acct = im.account_dict(login, rec["password"], address); acct["id"] = rec["account_id"]
    return {"account": mbx._public(acct), "address": address, "assigned_to": for_email if other else "", "note": note, "username": login, "password": pw, "username": login, "password": pw,
            "imap": {"host": acct["imap_host"], "port": acct["imap_port"]}, "smtp": {"host": acct["smtp_host"], "port": acct["smtp_port"]}, "message": f"{address} is ready."}

# ---------------------------------------------------------------- own domains
@router.get("/domains")
async def domains(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _ready()
    return {"domains": [_dom_view(r) for r in await _my_domains(db, user)], "mx": im.mx_host()}

@router.post("/domains")
async def add_domain(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _ready()
    try: dom = im.valid_domain(payload.get("domain"))
    except ValueError as exc: raise HTTPException(422, str(exc))
    mine = await _my_domains(db, user)
    existing = next((r for r in mine if r.value["domain"] == dom), None)
    if existing: return {**_dom_view(existing), "message": "That domain is already added."}
    if len(mine) >= (20 if user.role == "admin" else MAX_DOMAINS): raise HTTPException(422, f"You can add up to {MAX_DOMAINS} domains.")
    if any((r.value or {}).get("status") == "verified" for r in await _dom_rows(db, dom)): raise HTTPException(409, "That domain is already in use by someone else.")
    row = IntegrationSetting(key=f"{DOMAIN_PREFIX}{dom}:{user.id}", value={"domain": dom, "owner": user.id, "status": "pending", "token": im.new_token(), "added": datetime.now(timezone.utc).isoformat()})
    db.add(row); db.add(AuditLog(actor=user.email, action="isiftmail.domain.add", resource_type="mail", safe_metadata={"domain": dom})); await db.commit()
    return {**_dom_view(row), "message": "Domain added. Now add the records below at your domain registrar."}

@router.post("/domains/check")
async def check_domain(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Looks the records up on the internet. When the ownership record is there the domain is set up on the mail server and mailboxes can be made on it."""
    await _ready()
    dom = str(payload.get("domain") or "").strip().lower(); row = await _my_domain(db, user, dom)
    if not row: raise HTTPException(404, "Add that domain first.")
    v = dict(row.value); first = v.get("status") != "verified"
    try:
        checks = await im.check_dns(dom, v["token"], v.get("server"))
        if first:
            if not checks["owner"]: return {**_dom_view(row), "checks": checks, "verified": False, "message": "The ownership record is not visible yet. DNS changes can take a few minutes, sometimes longer. Check again soon."}
            if any((r.value or {}).get("status") == "verified" for r in await _dom_rows(db, dom)): raise HTTPException(409, "That domain is already in use by someone else.")
            await im.create_domain(dom); await im.create_dkim(dom)
            v["status"] = "verified"; v["verified_at"] = datetime.now(timezone.utc).isoformat()
        if not any(x["type"] == "TXT" and "_domainkey" in x["name"] for x in v.get("server") or []): v["server"] = await im.server_dns_records(dom)
        checks = await im.check_dns(dom, v["token"], v.get("server"))
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    row.value = v; await db.commit()
    if first: db.add(AuditLog(actor=user.email, action="isiftmail.domain.verify", resource_type="mail", safe_metadata={"domain": dom})); await db.commit()
    msg = ("Your domain is verified. You can now make addresses on it." if checks["mx"] else "Your domain is verified and you can make addresses on it, but mail will not arrive until the MX record is added.")
    return {**_dom_view(row), "checks": checks, "verified": True, "message": msg}

@router.delete("/domains")
async def remove_domain(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    dom = str(payload.get("domain") or "").strip().lower(); row = await _my_domain(db, user, dom)
    if not row: raise HTTPException(404, "That domain was not found.")
    if any((r.value or {}).get("domain") == dom for r in await _recs(db)): raise HTTPException(409, "Close the mailboxes on this domain first.")
    try:
        if (row.value or {}).get("status") == "verified": await im.remove_domain(dom)
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    await db.delete(row); db.add(AuditLog(actor=user.email, action="isiftmail.domain.remove", resource_type="mail", safe_metadata={"domain": dom})); await db.commit()
    return {"ok": True, "message": f"{dom} was removed."}

# ---------------------------------------------------------------- settings, drafts, password, closing
async def _settings(db: AsyncSession, user: User, aid: str) -> dict:
    row = await db.get(IntegrationSetting, _skey(user.id, aid)); v = dict(row.value or {}) if row else {}
    ar = v.get("autoreply") or {}
    return {"signature": v.get("signature", ""), "autoreply": {"on": bool(ar.get("on")), "subject": ar.get("subject", ""), "message": ar.get("message", ""), "start": ar.get("start", ""), "end": ar.get("end", "")}}

async def _store_settings(db: AsyncSession, user: User, aid: str, val: dict):
    row = await db.get(IntegrationSetting, _skey(user.id, aid))
    if row: row.value = val
    else: db.add(IntegrationSetting(key=_skey(user.id, aid), value=val))
    await db.commit()

async def _need(db: AsyncSession, user: User, aid: str = "") -> dict:
    mine = await _mine(db, user, aid)
    if not mine: raise HTTPException(404, "You do not have an isiftmail address yet.")
    return mine

@router.get("/settings")
async def get_settings(aid: str = "", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    mine = await _need(db, user, aid)
    return {"address": mine["address"], "id": mine["id"], "username": mine.get("username", ""), "imap": {"host": mine["imap_host"], "port": mine["imap_port"]},
            "smtp": {"host": mine["smtp_host"], "port": mine["smtp_port"]}, **await _settings(db, user, mine["id"])}

@router.put("/settings")
async def put_settings(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    mine = await _need(db, user, str(payload.get("aid") or ""))
    cur = await _settings(db, user, mine["id"]); new = {"signature": cur["signature"], "autoreply": cur["autoreply"]}
    if "signature" in payload: new["signature"] = str(payload.get("signature") or "").replace("\r\n", "\n").strip()[:1000]
    if "autoreply" in payload:
        a = payload.get("autoreply") or {}; on = bool(a.get("on"))
        ar = {"on": on, "subject": str(a.get("subject") or "").strip()[:120], "message": str(a.get("message") or "").strip()[:2000], "start": str(a.get("start") or "")[:10], "end": str(a.get("end") or "")[:10]}
        try: script = im.vacation_script(ar["subject"], ar["message"], ar["start"], ar["end"]) if on else None
        except ValueError as exc: raise HTTPException(422, str(exc))
        acct = await mbx._account(db, user, mine["id"])
        try: await im.apply_autoreply(acct, script)
        except mailer.MailError as exc: raise HTTPException(502, str(exc))
        new["autoreply"] = ar
    await _store_settings(db, user, mine["id"], new)
    db.add(AuditLog(actor=user.email, action="isiftmail.settings", resource_type="mail", safe_metadata={"autoreply": new["autoreply"]["on"]})); await db.commit()
    return {**new, "message": "Saved."}

@router.post("/password")
async def reset_password(payload: dict | None = None, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """A new password for using the mailbox in other apps (Outlook, a phone). iSift keeps working: it stores the new one."""
    mine = await _need(db, user, str((payload or {}).get("aid") or ""))
    pw = im.new_password()
    try: await im.set_password(mine["username"], pw)
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    items = await mbx._stored(db, user); await mbx._save(db, user, [dict(x, password=rs._enc(pw)) if x["id"] == mine["id"] else x for x in items])
    rec = await _rec(db, mine["address"])
    if rec: rec.value = {**rec.value, "password": rs._enc(pw)}
    db.add(AuditLog(actor=user.email, action="isiftmail.password", resource_type="mail")); await db.commit()
    return {"username": mine["username"], "password": pw, "message": "New password made. It is shown once."}

@router.post("/draft")
async def draft(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    mine = await _need(db, user, str(payload.get("aid") or ""))
    acct = await mbx._account(db, user, mine["id"])
    to, cc = mbx._addrs(payload.get("to")), mbx._addrs(payload.get("cc"))
    try: uid = await im.save_draft(acct, to, cc, str(payload.get("subject") or "")[:300], str(payload.get("body") or "")[:200_000], int(payload.get("replace_uid") or 0))
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    return {"uid": uid, "message": "Draft saved."}

@router.delete("/mailbox")
async def close(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Closes a mailbox for good: the address and every message in it are deleted from the mail server."""
    mine = await _need(db, user, str(payload.get("aid") or ""))
    if str(payload.get("confirm") or "").strip().lower() != mine["address"]: raise HTTPException(422, "Type the full address to confirm.")
    rec = await _rec(db, mine["address"])
    if rec and rec.value.get("owner") != user.id: raise HTTPException(403, "Only the administrator of this domain can close this mailbox.")
    await _close_box(db, user, mine["address"], mine["username"], mine["id"], rec)
    return {"ok": True, "message": f"{mine['address']} has been closed."}

async def _close_box(db: AsyncSession, actor: User, address: str, login: str, account_id: str, rec: IntegrationSetting | None):
    """Deletes the mailbox from the mail server and from whoever's Mail it appears in, and holds the name back."""
    try: await im.remove(login)
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    holder = await _user_by_email(db, (rec.value or {}).get("assignee", "")) if rec else actor
    for who in {u.id: u for u in (holder, actor) if u}.values():
        items = await mbx._stored(db, who)
        if any(x["address"] == address for x in items): await mbx._save(db, who, [x for x in items if x["address"] != address])
        srow = await db.get(IntegrationSetting, _skey(who.id, account_id))
        if srow: await db.delete(srow)
    if rec: await db.delete(rec)
    closed = await _closed(db); closed[address] = datetime.now(timezone.utc).isoformat()
    crow = await db.get(IntegrationSetting, CLOSED_KEY)
    if crow: crow.value = {"names": closed}
    else: db.add(IntegrationSetting(key=CLOSED_KEY, value={"names": closed}))
    db.add(AuditLog(actor=actor.email, action="isiftmail.close", resource_type="mail", safe_metadata={"address": address})); await db.commit()

# ---- the domain owner's view of every mailbox on their domain
async def _owned_rec(db: AsyncSession, user: User, address: str) -> IntegrationSetting:
    rec = await _rec(db, str(address or "").strip().lower())
    if not rec or rec.value.get("owner") != user.id: raise HTTPException(404, "That mailbox was not found on one of your domains.")
    return rec

@router.get("/domains/mailboxes")
async def domain_mailboxes(domain: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    dom = domain.strip().lower()
    if not await _my_domain(db, user, dom): raise HTTPException(404, "Add that domain first.")
    out = []
    for r in await _recs(db):
        v = r.value or {}
        if v.get("domain") != dom or v.get("owner") != user.id: continue
        out.append({"address": v["address"], "display": v.get("display", ""), "assignee": v.get("assignee", ""), "yours": v.get("assignee") == user.email.lower(),
                    "status": "waiting" if not v.get("claimed") else "active"})
    return {"mailboxes": sorted(out, key=lambda x: x["address"]), "limit": MAX_BOXES_PER_DOMAIN}

@router.post("/domains/mailboxes/password")
async def domain_mailbox_password(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rec = await _owned_rec(db, user, payload.get("address")); v = dict(rec.value); pw = im.new_password()
    try: await im.set_password(v["login"], pw)
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    v["password"] = rs._enc(pw); rec.value = v
    who = await _user_by_email(db, v.get("assignee", ""))
    if who:
        items = await mbx._stored(db, who)
        if any(x["address"] == v["address"] for x in items): await mbx._save(db, who, [dict(x, password=v["password"]) if x["address"] == v["address"] else x for x in items])
    db.add(AuditLog(actor=user.email, action="isiftmail.password", resource_type="mail", safe_metadata={"address": v["address"]})); await db.commit()
    return {"username": v["login"], "password": pw, "message": "New password made. Give it to the person. It is shown once."}

@router.delete("/domains/mailboxes")
async def domain_mailbox_close(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rec = await _owned_rec(db, user, payload.get("address")); v = rec.value
    if str(payload.get("confirm") or "").strip().lower() != v["address"]: raise HTTPException(422, "Type the full address to confirm.")
    await _close_box(db, user, v["address"], v["login"], v["account_id"], rec)
    return {"ok": True, "message": f"{v['address']} has been closed."}
