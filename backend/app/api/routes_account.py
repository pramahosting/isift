"""My account: profile, time and location, password, the company I belong to (with its people), and my alerts."""
import re, secrets
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal, hash_password, verify_password
from app.models import User, LocalAccount, AuditLog
from app.services import store, billing, datasets as ds

router = APIRouter(prefix="/api/v1", tags=["account"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLES = ("owner", "admin", "member")
PROFILE_TEXT = {"phone": 40, "job_title": 100, "department": 100, "city": 100, "country": 100, "language": 40, "bio": 500}

def _builtin(user: User) -> bool: return settings.is_local_demo and user.email == "admin@example.test"
def _em(v) -> str: return str(v or "").strip().lower()

async def _profile(db, email: str) -> dict:
    p = await store.get(db, store.hkey("profile", email), {})
    return {**{k: "" for k in PROFILE_TEXT}, "timezone": "", "work_days": [0, 1, 2, 3, 4], "work_start": "09:00", "work_end": "17:00", **p}

async def _company_of(db, email: str) -> dict | None:
    link = await store.get(db, store.hkey("memberof", email), {})
    if not link.get("company_id"): return None
    c = await store.get(db, f"company:{link['company_id']}", {})
    if not c or not any(m["email"] == _em(email) for m in c.get("members", [])): return None
    c["id"] = link["company_id"]; return c

async def _local_account(db, email: str):
    return (await db.execute(select(LocalAccount).where(LocalAccount.email == _em(email)))).scalar_one_or_none()

async def _company_view(db, c: dict | None, me: User) -> dict | None:
    if not c: return None
    mine = next((m for m in c["members"] if m["email"] == _em(me.email)), {})
    members = []
    for m in c["members"]:
        users = (await db.execute(select(User).where(User.email == m["email"]))).scalars().all()
        members.append({**m, "status": "active" if users or m["email"] == _em(me.email) else "invited", "name": (users[0].display_name if users else m.get("name", "")) or m.get("name", "")})
    return {"id": c["id"], "name": c["name"], "plan": await billing.plan_of(db, me), "plan_name": billing.PLANS[await billing.plan_of(db, me)]["name"], "my_role": mine.get("role", "member"), "members": members, "can_manage": mine.get("role") in ("owner", "admin"), "can_create_accounts": settings.is_local_demo}

@router.get("/account")
async def account(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    acct = await _local_account(db, user.email)
    return {"user": {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role},
            "profile": await _profile(db, user.email), "company": await _company_view(db, await _company_of(db, user.email), user),
            "password": {"can_change": bool(acct) or _builtin(user), "why": "" if (acct or _builtin(user)) else "You sign in with Microsoft, so your password is managed there."}}

@router.patch("/account")
async def update_account(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    p = await _profile(db, user.email)
    for k, n in PROFILE_TEXT.items():
        if k in payload: p[k] = str(payload[k] or "").strip()[:n]
    if "timezone" in payload:
        tz = str(payload["timezone"] or "").strip()
        if tz:
            try: ZoneInfo(tz)
            except Exception: raise HTTPException(422, "That time zone is not known.")
        p["timezone"] = tz
    if "work_days" in payload: p["work_days"] = sorted({int(d) for d in (payload["work_days"] or []) if str(d).isdigit() and 0 <= int(d) <= 6})
    for k in ("work_start", "work_end"):
        if k in payload:
            v = str(payload[k] or "")
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v): raise HTTPException(422, "Use times like 09:00.")
            p[k] = v
    if p["work_start"] >= p["work_end"]: raise HTTPException(422, "The working day must end after it starts.")
    if "display_name" in payload:
        name = str(payload["display_name"] or "").strip()
        if not 1 <= len(name) <= 100: raise HTTPException(422, "Enter your name (up to 100 characters).")
        user.display_name = name
        acct = await _local_account(db, user.email)
        if acct: acct.display_name = name
    await store.put(db, store.hkey("profile", user.email), p, commit=False)
    db.add(AuditLog(actor=user.email, action="account.update", resource_type="account", safe_metadata={})); await db.commit()
    return {"profile": p, "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}, "message": "Profile saved."}

@router.post("/account/password")
async def change_password(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    cur, new = str(payload.get("current") or ""), str(payload.get("new") or "")
    if not 8 <= len(new) <= 128: raise HTTPException(422, "The new password must be 8 to 128 characters.")
    if new == cur: raise HTTPException(422, "Choose a password that is different from the current one.")
    acct = await _local_account(db, user.email)
    if acct:
        if not verify_password(cur, acct.password_hash): raise HTTPException(403, "The current password is not right.")
        acct.password_hash = hash_password(new)
    elif _builtin(user):
        saved = await store.get(db, "admin_password", {})
        ok = verify_password(cur, saved["hash"]) if saved.get("hash") else secrets.compare_digest(cur, settings.local_admin_password)
        if not ok: raise HTTPException(403, "The current password is not right.")
        await store.put(db, "admin_password", {"hash": hash_password(new)}, commit=False)
    else: raise HTTPException(409, "You sign in with Microsoft, so your password is managed there.")
    db.add(AuditLog(actor=user.email, action="account.password", resource_type="account", safe_metadata={})); await db.commit()
    return {"message": "Password changed. Use it the next time you sign in."}

# ---------------- company ----------------
async def _my_company(db, user: User, manage: bool = False) -> dict:
    c = await _company_of(db, user.email)
    if not c: raise HTTPException(404, "You are not part of a company account yet.")
    if manage and not any(m["email"] == _em(user.email) and m["role"] in ("owner", "admin") for m in c["members"]):
        raise HTTPException(403, "Only the company owner or an administrator can do that.")
    return c

async def _save_company(db, c: dict):
    cid = c["id"]; await store.put(db, f"company:{cid}", {k: v for k, v in c.items() if k != "id"})

@router.post("/account/company", status_code=201)
async def create_company(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    if await _company_of(db, user.email): raise HTTPException(409, "You already belong to a company account.")
    name = str(payload.get("name") or "").strip()[:120]
    if not name: raise HTTPException(422, "Enter the company name.")
    plan = "basic"
    import uuid
    cid = uuid.uuid4().hex[:16]
    c = {"id": cid, "name": name, "plan": plan, "members": [{"email": _em(user.email), "name": user.display_name, "role": "owner"}]}
    await _save_company(db, c); await store.put(db, store.hkey("memberof", user.email), {"company_id": cid})
    mine = await store.get(db, store.hkey("billing", user.email), {})                       # a plan the person already pays for moves to the company
    if mine: await store.put(db, f"billing:co:{cid}", mine, commit=False); await store.drop(db, store.hkey("billing", user.email))
    db.add(AuditLog(actor=user.email, action="company.create", resource_type="company", resource_id=cid, safe_metadata={"plan": plan})); await db.commit()
    return await _company_view(db, c, user)

@router.patch("/account/company")
async def update_company(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _my_company(db, user, manage=True)
    if "name" in payload:
        n = str(payload["name"] or "").strip()[:120]
        if not n: raise HTTPException(422, "Enter the company name.")
        c["name"] = n
    await _save_company(db, c)
    return await _company_view(db, c, user)

@router.post("/account/company/members", status_code=201)
async def add_member(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _my_company(db, user, manage=True)
    email = _em(payload.get("email")); name = str(payload.get("name") or "").strip()[:100]
    role = payload.get("role") if payload.get("role") in ("admin", "member") else "member"
    if not EMAIL.match(email): raise HTTPException(422, "Enter a valid email address.")
    if any(m["email"] == email for m in c["members"]): raise HTTPException(409, "That person is already in the company.")
    if (await store.get(db, store.hkey("memberof", email), {})).get("company_id"): raise HTTPException(409, "That person already belongs to another company account.")
    temp = None
    if settings.is_local_demo and not await _local_account(db, email) and email != "admin@example.test":
        if not name: raise HTTPException(422, "Enter the person's name so their sign-in can be created.")
        temp = str(payload.get("password") or "") or secrets.token_urlsafe(9)
        if len(temp) < 8: raise HTTPException(422, "The password must be at least 8 characters.")
        try: await ds.create_local_user(db, email, name, temp, "user", True)
        except ValueError as exc: raise HTTPException(409 if "exists" in str(exc) else 422, str(exc))
    c["members"].append({"email": email, "name": name or email, "role": role}); await _save_company(db, c)
    await store.put(db, store.hkey("memberof", email), {"company_id": c["id"]})
    from app.services.notify import notify
    await notify(db, email, "company", f"You were added to {c['name']}", f"{user.display_name or user.email} added you to the company account.", "", user.display_name or user.email)
    db.add(AuditLog(actor=user.email, action="company.member.add", resource_type="company", resource_id=c["id"], safe_metadata={"role": role})); await db.commit()
    return {"company": await _company_view(db, c, user), "temp_password": temp if payload.get("password") in (None, "") else None,
            "message": f"{email} was added." + (" Give them the temporary password below; they can change it under My account." if temp else "")}

@router.patch("/account/company/members/{email}")
async def change_member(email: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _my_company(db, user, manage=True); email = _em(email)
    m = next((x for x in c["members"] if x["email"] == email), None)
    if not m: raise HTTPException(404, "That person is not in the company.")
    if m["role"] == "owner": raise HTTPException(409, "The company owner's role cannot be changed.")
    if payload.get("role") not in ("admin", "member"): raise HTTPException(422, "Role must be admin or member.")
    m["role"] = payload["role"]; await _save_company(db, c)
    return await _company_view(db, c, user)

@router.delete("/account/company/members/{email}")
async def remove_member(email: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _my_company(db, user); email = _em(email); me = _em(user.email)
    m = next((x for x in c["members"] if x["email"] == email), None)
    if not m: raise HTTPException(404, "That person is not in the company.")
    mine = next(x for x in c["members"] if x["email"] == me)
    if email != me and mine["role"] not in ("owner", "admin"): raise HTTPException(403, "Only the company owner or an administrator can remove people.")
    if m["role"] == "owner": raise HTTPException(409, "The owner cannot be removed. Delete the company or hand it over first.")
    if m["role"] == "admin" and email != me and mine["role"] != "owner": raise HTTPException(403, "Only the owner can remove an administrator.")
    c["members"] = [x for x in c["members"] if x["email"] != email]; await _save_company(db, c); await store.drop(db, store.hkey("memberof", email))
    return {"company": await _company_view(db, c, user) if email != me else None, "message": "You left the company." if email == me else f"{email} was removed from the company."}

@router.delete("/account/company")
async def delete_company(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _my_company(db, user)
    if not any(m["email"] == _em(user.email) and m["role"] == "owner" for m in c["members"]): raise HTTPException(403, "Only the owner can delete the company account.")
    for m in c["members"]: await store.drop(db, store.hkey("memberof", m["email"]))
    await store.drop(db, f"company:{c['id']}")
    return {"message": "The company account was deleted. People keep their own sign-ins."}

# ---------------- alerts ----------------
@router.get("/notifications")
async def notifications(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    items = (await store.get(db, store.hkey("notif", user.email), {"items": []})).get("items", [])
    return {"items": items[:30], "unread": sum(1 for i in items if not i.get("read"))}

@router.post("/notifications/read")
async def notifications_read(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    key = store.hkey("notif", user.email); rec = await store.get(db, key, {"items": []}); ids = set(payload.get("ids") or [])
    for i in rec.get("items", []):
        if payload.get("all") or i["id"] in ids: i["read"] = True
    await store.put(db, key, rec)
    return {"unread": sum(1 for i in rec["items"] if not i.get("read"))}

# ---------------- access keys (for the Outlook add-in and other applications) ----------------
from app.core.security import PAT_PREFIX, pat_hash
from app.models import IntegrationSetting
from sqlalchemy import select as _select

def _key_row(row) -> dict: return {"id": row.key[4:16], "name": row.value.get("name", ""), "created": row.value.get("created"), "last4": row.value.get("last4", ""), "revoked": bool(row.value.get("revoked"))}

@router.get("/account/access-keys")
async def list_access_keys(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(_select(IntegrationSetting).where(IntegrationSetting.key.like("pat:%")))).scalars().all()
    return {"keys": [_key_row(r) for r in rows if r.value and r.value.get("email") == _em(user.email) and not r.value.get("revoked")]}

@router.post("/account/access-keys", status_code=201)
async def create_access_key(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """A personal key for an add-in or another application. It is shown once, stored only as a hash, and can reach scheduling and meeting creation, nothing else."""
    from datetime import datetime, timezone
    name = str(payload.get("name") or "").strip()[:80]
    if not name: raise HTTPException(422, "Give the key a name, for example Outlook add-in.")
    rows = (await db.execute(_select(IntegrationSetting).where(IntegrationSetting.key.like("pat:%")))).scalars().all()
    if sum(1 for r in rows if r.value and r.value.get("email") == _em(user.email) and not r.value.get("revoked")) >= 10: raise HTTPException(409, "You already have 10 keys. Remove one first.")
    token = PAT_PREFIX + secrets.token_urlsafe(32)
    db.add(IntegrationSetting(key="pat:" + pat_hash(token), value={"email": _em(user.email), "name": name, "created": datetime.now(timezone.utc).isoformat(), "last4": token[-4:], "revoked": False}))
    db.add(AuditLog(actor=user.email, action="account.access_key_created", resource_type="account", safe_metadata={"name": name})); await db.commit()
    return {"key": token, "id": pat_hash(token)[:12], "name": name}

@router.delete("/account/access-keys/{kid}")
async def revoke_access_key(kid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(_select(IntegrationSetting).where(IntegrationSetting.key.like("pat:%")))).scalars().all()
    for r in rows:
        if r.key[4:16] == kid and r.value and r.value.get("email") == _em(user.email):
            r.value = {**r.value, "revoked": True}; db.add(AuditLog(actor=user.email, action="account.access_key_revoked", resource_type="account", safe_metadata={"name": r.value.get("name")})); await db.commit(); return {"ok": True}
    raise HTTPException(404, "No such key.")
