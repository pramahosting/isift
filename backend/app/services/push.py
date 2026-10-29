"""Web Push: alerts that reach a computer or phone even when iSift is closed (the way Zoom does it).
A person turns notifications on once in the browser; their device is remembered here. Then:
  * a meeting is about to start / is starting now,
  * an invitation or shared item arrives (sent from notify.notify),
  * new mail arrives in a connected inbox.
The signing keys are made automatically the first time and kept in the database, so nothing has to be set up."""
import asyncio, base64, json, logging, time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models import IntegrationSetting, Meeting, User
from app.services import store

log = logging.getLogger("isift")
VAPID_KEY = "vapid_keys"
SUBJECT = "mailto:info@isift.au"
MAX_DEVICES = 8
MAIL_EVERY = 120

def _enc(s): from app.core import runtime_settings as rs; return rs._enc(s)
def _dec(s): from app.core import runtime_settings as rs; return rs._dec(s)

async def vapid(db):
    """(private PEM, public key for the browser). Made once and kept."""
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    row = await db.get(IntegrationSetting, VAPID_KEY)
    if row and row.value and row.value.get("private"):
        pem = _dec(row.value["private"]); v = Vapid.from_pem(pem.encode())
    else:
        v = Vapid(); v.generate_keys(); pem = v.private_pem().decode()
        val = {"private": _enc(pem)}
        if row: row.value = val
        else: db.add(IntegrationSetting(key=VAPID_KEY, value=val))
        await db.commit()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return pem, base64.urlsafe_b64encode(pub).rstrip(b"=").decode()

def _key(email): return store.hkey("push", email)

async def subs(db, email) -> dict:
    return await store.get(db, _key(email), {"email": email.lower(), "subs": [], "sent": {}, "mail": {}})

async def add_sub(db, email, sub: dict, ua: str = ""):
    rec = await subs(db, email); rec["email"] = email.lower()
    rec["subs"] = [s for s in rec.get("subs", []) if s.get("endpoint") != sub["endpoint"]]
    rec["subs"].insert(0, {"endpoint": sub["endpoint"], "keys": sub["keys"], "ua": ua[:120], "at": datetime.now(timezone.utc).isoformat()})
    rec["subs"] = rec["subs"][:MAX_DEVICES]
    await store.put(db, _key(email), rec)

async def remove_sub(db, email, endpoint: str):
    rec = await subs(db, email); rec["subs"] = [s for s in rec.get("subs", []) if s.get("endpoint") != endpoint]
    await store.put(db, _key(email), rec)

def _send_one(sub: dict, payload: str, pem: str) -> int:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]}, data=payload, vapid_private_key=Vapid.from_pem(pem.encode()), vapid_claims={"sub": SUBJECT}, ttl=3600)
        return 201
    except WebPushException as e:
        return getattr(getattr(e, "response", None), "status_code", 0) or 0
    except Exception:
        return 0

async def send(db, email: str, title: str, body: str = "", url: str = "", tag: str = "", kind: str = "") -> int:
    """Sends to every device of this person. Devices the push service says are gone are forgotten. Returns how many were reached."""
    rec = await subs(db, email); devices = rec.get("subs", [])
    if not devices: return 0
    pem, _ = await vapid(db)
    payload = json.dumps({"title": title[:120], "body": body[:240], "url": url, "tag": tag or kind or "isift", "kind": kind})
    codes = await asyncio.gather(*[asyncio.to_thread(_send_one, s, payload, pem) for s in devices])
    ok = sum(1 for c in codes if c in (200, 201, 202))
    dead = {s["endpoint"] for s, c in zip(devices, codes) if c in (404, 410)}
    if dead:
        rec["subs"] = [s for s in devices if s["endpoint"] not in dead]; await store.put(db, _key(email), rec)
    return ok

async def safe_send(db, email, title, body="", url="", tag="", kind=""):
    try: return await asyncio.wait_for(send(db, email, title, body, url, tag, kind), 10)
    except Exception: log.warning("Push to %s did not go through", email, exc_info=False); return 0

# ------------------------------------------------------------------ the background check
def _once(rec: dict, k: str) -> bool:
    """True the first time a notice key is seen (and remembers it for two days)."""
    sent = rec.setdefault("sent", {}); now = time.time()
    for x in [x for x, t in sent.items() if now - t > 172800]: sent.pop(x, None)
    if k in sent: return False
    sent[k] = now; return True

async def _meetings(db, rec: dict, user: User) -> bool:
    now = datetime.now(timezone.utc); changed = False
    rows = (await db.execute(select(Meeting).where(Meeting.owner_id == user.id, Meeting.status != "cancelled", Meeting.start_at <= now + timedelta(minutes=6), Meeting.start_at >= now - timedelta(minutes=5)))).scalars().all()
    for m in rows:
        st = m.start_at if m.start_at.tzinfo else m.start_at.replace(tzinfo=timezone.utc); mins = (st - now).total_seconds() / 60
        url = m.join_url or ""
        if 0.5 < mins <= 5.5 and _once(rec, f"{m.id}@{st.isoformat()}:soon"):
            changed = True; await safe_send(db, user.email, m.title or "Meeting", f"Starts in {max(1, round(mins))} min", url, f"meeting-{m.id}", "meeting")
        elif mins <= 0.5 and _once(rec, f"{m.id}@{st.isoformat()}:now"):
            changed = True; await safe_send(db, user.email, m.title or "Meeting", "Starting now. Tap to join." if url else "Starting now", url, f"meeting-{m.id}", "meeting")
    return changed

async def _mail(db, rec: dict, user: User) -> bool:
    from app.api.routes_mailbox import _stored, _account
    from app.integrations import mailbox as mb
    now = time.time()
    if now - rec.get("mail_at", 0) < MAIL_EVERY: return False
    rec["mail_at"] = now; seen = rec.setdefault("mail", {}); changed = True
    try: accounts = (await _stored(db, user))[:4]
    except Exception: return changed
    for a in accounts:
        try:
            acct = await _account(db, user, a["id"])
            res = await asyncio.wait_for(mb.messages(acct, "INBOX", "", 6, 0), 25)
        except Exception: continue
        msgs = res.get("messages", []); top = max((m["uid"] for m in msgs), default=0)
        last = seen.get(a["id"])
        seen[a["id"]] = max(top, last or 0)
        if last is None: continue                      # first look only records where the inbox is, so old mail is never announced
        fresh = [m for m in msgs if m["uid"] > last and m.get("unread", True)]
        for m in sorted(fresh, key=lambda m: m["uid"])[:3]:
            await safe_send(db, user.email, (m.get("from") or "New email")[:80], (m.get("subject") or "(no subject)")[:140], "#/commbox", f"mail-{a['id']}-{m['uid']}", "mail")
        if len(fresh) > 3: await safe_send(db, user.email, "iSift", f"{len(fresh) - 3} more new emails", "#/commbox", f"mail-{a['id']}-more", "mail")
    return changed

async def tick(db) -> int:
    rows = (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like("push:%")))).scalars().all()
    n = 0
    for row in rows:
        rec = dict(row.value or {})
        if not rec.get("subs") or not rec.get("email"): continue
        user = (await db.execute(select(User).where(User.email == rec["email"]))).scalar_one_or_none()
        if not user: continue
        c1 = await _meetings(db, rec, user); c2 = await _mail(db, rec, user)
        if c1 or c2:
            fresh = await db.get(IntegrationSetting, row.key)
            keep = dict(fresh.value or {}) if fresh else rec          # the device list may have changed while we were sending
            keep.update({"sent": rec.get("sent", {}), "mail": rec.get("mail", {}), "mail_at": rec.get("mail_at", 0)})
            if fresh: fresh.value = keep
            await db.commit(); n += 1
    return n

async def loop():
    await asyncio.sleep(20)
    while True:
        try:
            async with SessionLocal() as db: await tick(db)
        except asyncio.CancelledError: raise
        except Exception: log.exception("Push check failed")
        await asyncio.sleep(30)
