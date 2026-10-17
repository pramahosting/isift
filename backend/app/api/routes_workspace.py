"""Contacts, groups, chat, docs and whiteboards, and the personal meeting ID."""
import re, secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.models import User, Contact, ContactGroup, Channel, ChatMessage, Note, Room

router = APIRouter(prefix="/api/v1", tags=["workspace"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _utc(d: datetime) -> str:
    return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d).isoformat()

# ---------------- contacts ----------------
async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    if not email: return None
    return (await db.execute(select(User).where(func.lower(User.email) == email.lower(), User.is_active == True))).scalars().first()  # noqa: E712

async def _contact_out(db: AsyncSession, c: Contact) -> dict:
    u = await _user_by_email(db, c.email)
    return {"id": c.id, "name": c.name, "email": c.email, "phone": c.phone, "account": c.account or "", "user_id": u.id if u else None}

def _clean_contact(p: dict) -> tuple[str, str, str]:
    name = str(p.get("name") or "").strip()[:200]; email = str(p.get("email") or "").strip().lower()[:320]; phone = str(p.get("phone") or "").strip()[:60]
    if not name: raise HTTPException(422, "Enter a name.")
    if email and not EMAIL.match(email): raise HTTPException(422, "That email address does not look right.")
    return name, email, phone

async def import_contacts(db: AsyncSession, user: User, items: list[dict], account: str = "") -> dict:
    """Add contacts that are not there yet in that account's list (matched by email, or by name when there is no email)."""
    account = (account or "").strip().lower()[:320]
    have = (await db.execute(select(Contact).where(Contact.owner_id == user.id, Contact.account == account))).scalars().all()
    emails = {c.email for c in have if c.email}; names = {c.name.lower() for c in have if not c.email}
    added = skipped = 0
    for it in items[:2000]:
        try: name, email, phone = _clean_contact(it)
        except HTTPException: skipped += 1; continue
        if (email and email in emails) or (not email and name.lower() in names): skipped += 1; continue
        db.add(Contact(owner_id=user.id, name=name, email=email, phone=phone, account=account)); added += 1
        if email: emails.add(email)
        else: names.add(name.lower())
    await db.commit()
    return {"added": added, "skipped": skipped}

def parse_contacts_csv(text: str) -> list[dict]:
    """Reads the CSV that Outlook exports (File > Open & Export > Import/Export > Export to a file > CSV) or any CSV with name and email columns."""
    import csv, io
    text = text.lstrip("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text)))
    def pick(r, *keys):
        low = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
        for k in keys:
            if low.get(k): return low[k]
        return ""
    out = []
    for r in rows:
        name = pick(r, "name", "display name", "full name") or " ".join(x for x in (pick(r, "first name"), pick(r, "middle name"), pick(r, "last name")) if x)
        email = pick(r, "e-mail address", "email address", "email", "e-mail", "e-mail 1 value", "e-mail 2 address")
        phone = pick(r, "mobile phone", "phone", "primary phone", "business phone", "home phone", "phone 1 - value")
        if not name and email: name = email
        if name: out.append({"name": name, "email": email, "phone": phone})
    return out

@router.post("/contacts/import-csv")
async def import_contacts_csv(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    text = str(payload.get("text") or "")
    if len(text) > 3_000_000: raise HTTPException(413, "That file is too large.")
    items = parse_contacts_csv(text)
    if not items: raise HTTPException(422, "No contacts found. Use the CSV file exported from Outlook, with name and e-mail columns.")
    r = await import_contacts(db, user, items, str(payload.get("account") or ""))
    return {**r, "message": f"{r['added']} contacts added, {r['skipped']} already there or skipped."}

@router.post("/contacts/merge")
async def merge_contacts(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Copy every account's contacts into one iSift list, once per person (same email, or same name when there is no email)."""
    rows = (await db.execute(select(Contact).where(Contact.owner_id == user.id).order_by(Contact.created_at))).scalars().all()
    local = [c for c in rows if not c.account]; emails = {c.email for c in local if c.email}; names = {c.name.lower() for c in local if not c.email}
    added = 0
    for c in rows:
        if not c.account: continue
        if (c.email and c.email in emails) or (not c.email and c.name.lower() in names): continue
        db.add(Contact(owner_id=user.id, name=c.name, email=c.email, phone=c.phone, account="")); added += 1
        if c.email: emails.add(c.email)
        else: names.add(c.name.lower())
    await db.commit()
    return {"added": added, "message": f"{added} contacts merged into your iSift list." if added else "Everything is already merged."}

@router.get("/contacts")
async def list_contacts(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Contact).where(Contact.owner_id == user.id).order_by(func.lower(Contact.name)))).scalars().all()
    groups = (await db.execute(select(ContactGroup).where(ContactGroup.owner_id == user.id).order_by(func.lower(ContactGroup.name)))).scalars().all()
    return {"contacts": [await _contact_out(db, c) for c in rows], "groups": [{"id": g.id, "name": g.name, "contact_ids": g.contact_ids or []} for g in groups]}

@router.post("/contacts")
async def add_contact(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    name, email, phone = _clean_contact(payload)
    account = str(payload.get("account") or "").strip().lower()[:320]
    if email and (await db.execute(select(Contact).where(Contact.owner_id == user.id, Contact.email == email, Contact.account == account))).scalars().first():
        raise HTTPException(409, "You already have a contact with that email address in this list.")
    c = Contact(owner_id=user.id, name=name, email=email, phone=phone, account=account); db.add(c); await db.commit()
    return await _contact_out(db, c)

async def _own_contact(db, user, cid) -> Contact:
    c = await db.get(Contact, cid)
    if not c or c.owner_id != user.id: raise HTTPException(404, "Contact not found")
    return c

@router.patch("/contacts/{cid}")
async def edit_contact(cid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _own_contact(db, user, cid)
    c.name, c.email, c.phone = _clean_contact({**{"name": c.name, "email": c.email, "phone": c.phone}, **payload}); await db.commit()
    return await _contact_out(db, c)

@router.delete("/contacts/{cid}")
async def delete_contact(cid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    c = await _own_contact(db, user, cid)
    for g in (await db.execute(select(ContactGroup).where(ContactGroup.owner_id == user.id))).scalars().all():
        if cid in (g.contact_ids or []): g.contact_ids = [x for x in g.contact_ids if x != cid]
    await db.delete(c); await db.commit(); return {"ok": True}

@router.post("/contact-groups")
async def add_group(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    name = str(payload.get("name") or "").strip()[:120]
    if not name: raise HTTPException(422, "Give the group a name.")
    g = ContactGroup(owner_id=user.id, name=name, contact_ids=await _valid_ids(db, user, payload.get("contact_ids"))); db.add(g); await db.commit()
    return {"id": g.id, "name": g.name, "contact_ids": g.contact_ids}

async def _valid_ids(db, user, ids) -> list:
    mine = {c for c in (await db.execute(select(Contact.id).where(Contact.owner_id == user.id))).scalars().all()}
    return [i for i in dict.fromkeys(ids or []) if i in mine]

@router.patch("/contact-groups/{gid}")
async def edit_group(gid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    g = await db.get(ContactGroup, gid)
    if not g or g.owner_id != user.id: raise HTTPException(404, "Group not found")
    if "name" in payload:
        n = str(payload["name"] or "").strip()[:120]
        if not n: raise HTTPException(422, "Give the group a name.")
        g.name = n
    if "contact_ids" in payload: g.contact_ids = await _valid_ids(db, user, payload["contact_ids"])
    await db.commit(); return {"id": g.id, "name": g.name, "contact_ids": g.contact_ids}

@router.delete("/contact-groups/{gid}")
async def delete_group(gid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    g = await db.get(ContactGroup, gid)
    if not g or g.owner_id != user.id: raise HTTPException(404, "Group not found")
    await db.delete(g); await db.commit(); return {"ok": True}

# ---------------- chat ----------------
async def _my_channel(db, user, cid) -> Channel:
    ch = await db.get(Channel, cid)
    if not ch or user.id not in (ch.member_ids or []): raise HTTPException(404, "Conversation not found")
    return ch

async def _channel_out(db, user, ch: Channel) -> dict:
    members = [(u.id, u.display_name or u.email) for u in (await db.execute(select(User).where(User.id.in_(ch.member_ids or [])))).scalars().all()]
    others = [n for i, n in members if i != user.id]
    last = (await db.execute(select(ChatMessage).where(ChatMessage.channel_id == ch.id).order_by(ChatMessage.created_at.desc()).limit(1))).scalars().first()
    return {"id": ch.id, "kind": ch.kind, "name": ch.name or ", ".join(others) or "Just you", "members": [n for _, n in members],
            "last": ({"text": last.text[:80], "at": _utc(last.created_at), "sender": last.sender_name} if last else None), "updated": _utc(last.created_at if last else ch.created_at)}

@router.get("/chat/channels")
async def list_channels(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = [c for c in (await db.execute(select(Channel))).scalars().all() if user.id in (c.member_ids or [])]
    out = [await _channel_out(db, user, c) for c in rows]
    return sorted(out, key=lambda c: c["updated"], reverse=True)

@router.post("/chat/channels")
async def open_channel(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Start (or reopen) a conversation with contacts or a contact group. People must have an iSift account to chat."""
    ids = await _valid_ids(db, user, payload.get("contact_ids"))
    if payload.get("group_id"):
        g = await db.get(ContactGroup, payload["group_id"])
        if g and g.owner_id == user.id: ids = list(dict.fromkeys(ids + await _valid_ids(db, user, g.contact_ids)))
    if not ids: raise HTTPException(422, "Choose at least one contact.")
    members, missing = {user.id}, []
    for cid in ids:
        c = await db.get(Contact, cid); u = await _user_by_email(db, c.email)
        if u: members.add(u.id)
        else: missing.append(c.name)
    if len(members) < 2: raise HTTPException(409, f"{', '.join(missing)} {'has' if len(missing)==1 else 'have'} no iSift account yet, so chat is not available. You can still invite by email from a meeting.")
    mem = sorted(members)
    if len(mem) == 2 and not payload.get("name"):
        for c in (await db.execute(select(Channel).where(Channel.kind == "direct"))).scalars().all():
            if sorted(c.member_ids or []) == mem: return {**await _channel_out(db, user, c), "skipped": missing}
    ch = Channel(kind="direct" if len(mem) == 2 and not payload.get("name") else "group", name=str(payload.get("name") or "").strip()[:200], member_ids=mem, created_by=user.id)
    db.add(ch); await db.commit()
    return {**await _channel_out(db, user, ch), "skipped": missing}

@router.get("/chat/channels/{cid}/messages")
async def channel_messages(cid: str, after: str | None = None, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _my_channel(db, user, cid)
    q = select(ChatMessage).where(ChatMessage.channel_id == cid).order_by(ChatMessage.created_at.desc()).limit(200)
    rows = list(reversed((await db.execute(q)).scalars().all()))
    if after: rows = rows[[m.id for m in rows].index(after) + 1:] if after in [m.id for m in rows] else rows
    return [{"id": m.id, "sender_id": m.sender_id, "sender": m.sender_name, "text": m.text, "at": _utc(m.created_at), "me": m.sender_id == user.id} for m in rows]

@router.post("/chat/channels/{cid}/messages")
async def send_message(cid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _my_channel(db, user, cid)
    text = str(payload.get("text") or "").strip()[:4000]
    if not text: raise HTTPException(422, "Type a message first.")
    m = ChatMessage(channel_id=cid, sender_id=user.id, sender_name=user.display_name or user.email, text=text); db.add(m); await db.commit()
    return {"id": m.id}

# ---------------- docs and whiteboards ----------------
def _note_out(n: Note, full=True) -> dict:
    d = {"id": n.id, "kind": n.kind, "title": n.title, "updated_at": _utc(n.updated_at)}
    if full: d["content"] = n.content
    return d

@router.get("/notes")
async def list_notes(kind: str = "doc", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Note).where(Note.owner_id == user.id, Note.kind == kind).order_by(Note.updated_at.desc()))).scalars().all()
    return [_note_out(n, False) for n in rows]

@router.post("/notes")
async def new_note(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    kind = "board" if payload.get("kind") == "board" else "doc"
    n = Note(owner_id=user.id, kind=kind, title=(str(payload.get("title") or "").strip() or "Untitled")[:200], content=str(payload.get("content") or "")[:2_000_000]); db.add(n); await db.commit()
    return _note_out(n)

async def _own_note(db, user, nid) -> Note:
    n = await db.get(Note, nid)
    if not n or n.owner_id != user.id: raise HTTPException(404, "Not found")
    return n

@router.get("/notes/{nid}")
async def get_note(nid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    return _note_out(await _own_note(db, user, nid))

@router.put("/notes/{nid}")
async def save_note(nid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n = await _own_note(db, user, nid)
    if "title" in payload: n.title = (str(payload["title"] or "").strip() or "Untitled")[:200]
    if "content" in payload: n.content = str(payload["content"] or "")[:2_000_000]
    n.updated_at = datetime.now(timezone.utc); await db.commit(); return _note_out(n, False)

@router.delete("/notes/{nid}")
async def delete_note(nid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await db.delete(await _own_note(db, user, nid)); await db.commit(); return {"ok": True}

# ---------------- personal meeting ID ----------------
async def get_pmi(db: AsyncSession, user: User, base_url: str = "") -> Room:
    """Each person has one permanent room (their Personal Meeting ID) that is never ended."""
    for r in (await db.execute(select(Room).where(Room.host_id == user.id, Room.meeting_id.is_(None)))).scalars().all():
        if (r.options or {}).get("pmi"): return r
    from app.api.routes_rooms import clean_access
    from app.core import runtime_settings as rs
    await rs.apply_overrides(db)
    for _ in range(20):
        code = "".join(secrets.choice("0123456789") for _ in range(10))
        if not (await db.execute(select(Room).where(Room.code == code))).scalars().first(): break
    access, pw = clean_access("passcode", None)
    r = Room(code=code, host_id=user.id, meeting_id=None, title=f"{user.display_name or user.email}'s Personal Meeting Room", access=access, passcode=pw, waiting_room=True, allow_guests=True, options={"pmi": True})
    db.add(r); await db.commit(); return r

async def set_pmi_open(db: AsyncSession, r: Room, on: bool):
    """Open room: no passcode and no admitting, anyone can start or join at any time. Off: back to a passcode and a waiting room."""
    from app.api.routes_rooms import clean_access
    r.options = {**(r.options or {}), "open_room": on}
    if on: r.access, r.passcode, r.waiting_room, r.allow_guests = "open", None, False, True
    else: r.access, r.passcode = clean_access("passcode", None); r.waiting_room = True
    await db.commit()

def _pmi_out(r: Room) -> dict:
    c = r.code
    return {"code": c, "pretty": f"{c[:3]} {c[3:6]} {c[6:]}", "passcode": r.passcode, "access": r.access, "waiting_room": r.waiting_room, "open_room": bool((r.options or {}).get("open_room"))}

@router.get("/me/pmi")
async def my_pmi(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    return _pmi_out(await get_pmi(db, user))

@router.patch("/me/pmi")
async def my_pmi_set(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    r = await get_pmi(db, user)
    if "open_room" in payload: await set_pmi_open(db, r, bool(payload["open_room"]))
    return _pmi_out(r)
