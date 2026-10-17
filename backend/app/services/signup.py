"""Sign-up with email verification. The account is only created after the person types the 6-digit code sent to their email, so an unverified address can never log in."""
import asyncio, hashlib, hmac, logging, re, secrets
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.security import hash_password
from app.services import store, countries

log = logging.getLogger("isift")
TTL = timedelta(minutes=15); MAX_TRIES = 5; RESEND_AFTER = timedelta(seconds=30); MAX_SENDS = 5
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

class SignupError(Exception):
    def __init__(self, message, code="invalid", status=422): super().__init__(message); self.message, self.code, self.status = message, code, status

def _key(email): return store.hkey("pendingsignup", email)
def _h(email, code): return hashlib.sha256(f"{settings.local_auth_secret}|{email}|{code}".encode()).hexdigest()
def _now(): return datetime.now(timezone.utc)

def validate(p: dict) -> dict:
    first, last = str(p.get("first_name", "")).strip(), str(p.get("last_name", "")).strip()
    email, pw = str(p.get("email", "")).strip().lower(), str(p.get("password", ""))
    if not 1 <= len(first) <= 60: raise SignupError("Enter your first name.")
    if not 1 <= len(last) <= 60: raise SignupError("Enter your last name.")
    if not EMAIL.fullmatch(email) or len(email) > 254: raise SignupError("Enter a valid email address.")
    if email in ("admin", "admin@example.test"): raise SignupError("That email is reserved. Use a different one.", "exists", 409)
    if not 8 <= len(pw) <= 128: raise SignupError("Password must be 8 to 128 characters.")
    country = str(p.get("country", "")).strip().upper()
    if country not in countries.BY_CODE: raise SignupError("Choose your country.")
    try: phone = countries.normalise_phone(country, p.get("phone"))
    except ValueError as exc: raise SignupError(str(exc))
    if not p.get("agree"): raise SignupError("Please accept the terms to create an account.")
    return {"first": first, "last": last, "email": email, "password": pw, "country": country, "phone": phone}

def app_sender() -> dict | None:
    """The app's own email account (Admin settings > Email and calendar). A user name and password are optional for servers that do not need them."""
    if not (settings.smtp_host and (settings.smtp_from or settings.smtp_user)): return None
    frm = settings.smtp_from or settings.smtp_user
    return {"address": frm, "from": frm, "username": settings.smtp_user, "password": settings.smtp_password, "smtp_host": settings.smtp_host, "smtp_port": settings.smtp_port}

async def send_code(db, email: str, name: str, code: str) -> bool:
    """Email the code from the app's own email account. Returns False when no email account is set up."""
    acct = app_sender()
    if not acct:
        log.warning("Sign-up code for %s is %s (no email account is set up in Admin settings, so it was not emailed).", email, code); return False
    from app.integrations import mail
    await mail.send(acct, [email], "Your iSift verification code", f"Hi {name},\n\nYour iSift verification code is {code}.\nIt works for 15 minutes. If you did not sign up, ignore this email.\n\n— iSift")
    return True


FAST = 4.0          # seconds the request waits for the mail server before answering "sending" and carrying on in the background

async def _deliver(email: str, name: str, code: str, code_hash: str) -> dict:
    """Send the message (slow: it talks to the mail server) and record the outcome on the pending sign-up."""
    from app.core.db import SessionLocal
    try:
        async with SessionLocal() as db:
            emailed = await send_code(db, email, name, code); state = {"state": "sent" if emailed else "none"}
    except Exception as exc:
        log.warning("verification email to %s failed: %s", email, exc); state = {"state": "failed", "error": str(exc)[:160]}
    try:
        async with SessionLocal() as db:
            rec = await store.get(db, _key(email), {})
            if rec and rec.get("code") == code_hash: rec["mail"] = state; await store.put(db, _key(email), rec)
    except Exception: log.exception("could not record the mail result")
    return state

async def _send(db, email, name, code, code_hash, drop_on_fail):
    task = asyncio.create_task(_deliver(email, name, code, code_hash))
    done, _ = await asyncio.wait({task}, timeout=FAST)
    if not done: return {"email": email, "emailed": "pending", "expires_minutes": 15}          # the browser follows up with /auth/signup/status
    st = task.result()
    if st["state"] == "failed":
        if drop_on_fail: await store.drop(db, _key(email))
        raise SignupError("We could not send the verification email (" + st["error"][:120] + "). Check the address, or ask your administrator to check the email settings.", "mail_failed", 502)
    return {"email": email, "emailed": st["state"] == "sent", "expires_minutes": 15}

async def status(db, email: str) -> dict:
    rec = await store.get(db, _key(str(email or "").strip().lower()), {})
    m = rec.get("mail") or {"state": "none"} if rec else {"state": "gone"}
    return {"state": m["state"], "error": m.get("error", "")}

async def start(db, p: dict) -> dict:
    from sqlalchemy import select
    from app.models import LocalAccount
    d = validate(p)
    if (await db.execute(select(LocalAccount).where(LocalAccount.email == d["email"]))).scalar_one_or_none():
        raise SignupError("An account with this email already exists. Log in instead.", "exists", 409)
    old = await store.get(db, _key(d["email"]), {})
    if old and datetime.fromisoformat(old["sent"]) + RESEND_AFTER > _now(): raise SignupError("A code was just sent. Wait a few seconds before asking for another.", "wait", 429)
    code = f"{secrets.randbelow(10**6):06d}"
    rec = {"first": d["first"], "last": d["last"], "country": d["country"], "phone": d["phone"], "pw": hash_password(d["password"]), "code": _h(d["email"], code), "tries": 0,
           "sent": _now().isoformat(), "expires": (_now() + TTL).isoformat(), "sends": int(old.get("sends", 0)) + 1 if old else 1}
    rec["codes"] = ([rec["code"]] + [c for c in old.get("codes", [old.get("code")]) if c])[:3]       # a slow mailbox may deliver an earlier email last: the last 3 codes all work
    if rec["sends"] > MAX_SENDS: raise SignupError("Too many codes were requested. Try again later.", "wait", 429)
    rec["mail"] = {"state": "pending"}
    await store.put(db, _key(d["email"]), rec)
    return await _send(db, d["email"], d["first"], code, rec["code"], drop_on_fail=True)

async def resend(db, email: str) -> dict:
    email = str(email or "").strip().lower(); rec = await store.get(db, _key(email), {})
    if not rec: raise SignupError("Start the sign-up again.", "expired", 404)
    if datetime.fromisoformat(rec["sent"]) + RESEND_AFTER > _now(): raise SignupError("A code was just sent. Wait a few seconds before asking for another.", "wait", 429)
    if rec["sends"] >= MAX_SENDS: raise SignupError("Too many codes were requested. Try again later.", "wait", 429)
    code = f"{secrets.randbelow(10**6):06d}"
    rec.update(code=_h(email, code), tries=0, sent=_now().isoformat(), expires=(_now() + TTL).isoformat(), sends=rec["sends"] + 1)
    rec["codes"] = ([rec["code"]] + [c for c in rec.get("codes", []) if c != rec["code"]])[:3]
    rec["mail"] = {"state": "pending"}
    await store.put(db, _key(email), rec)
    return await _send(db, email, rec["first"], code, rec["code"], drop_on_fail=False)

async def verify(db, email: str, code: str):
    """Returns the new LocalAccount once the code is right."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.models import LocalAccount, AuditLog
    email = str(email or "").strip().lower(); code = "".join(ch for ch in str(code or "") if ch.isdigit())
    rec = await store.get(db, _key(email), {})
    if not rec: raise SignupError("That code has expired. Start the sign-up again.", "expired", 404)
    if datetime.fromisoformat(rec["expires"]) < _now(): await store.drop(db, _key(email)); raise SignupError("That code has expired. Start the sign-up again.", "expired", 410)
    if rec["tries"] >= MAX_TRIES: await store.drop(db, _key(email)); raise SignupError("Too many wrong codes. Start the sign-up again.", "locked", 429)
    if not any(hmac.compare_digest(c, _h(email, code)) for c in (rec.get("codes") or [rec["code"]])):
        rec["tries"] += 1; await store.put(db, _key(email), rec); raise SignupError(f"That code is not right. {MAX_TRIES - rec['tries']} tries left.", "bad_code", 400)
    name = f"{rec['first']} {rec['last']}"
    account = LocalAccount(email=email, display_name=name, password_hash=rec["pw"]); db.add(account)
    cn = countries.BY_CODE[rec["country"]]["name"]
    await store.put(db, store.hkey("profile", email), {"phone": rec["phone"], "country": cn, "country_code": rec["country"], "first_name": rec["first"], "last_name": rec["last"], "email_verified": True}, commit=False)
    db.add(AuditLog(actor=email, action="auth.signup", resource_type="account", safe_metadata={"verified": True}))
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise SignupError("An account with this email already exists. Log in instead.", "exists", 409)
    await store.drop(db, _key(email))
    return account
