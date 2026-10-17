"""Who can do what with a shared note or whiteboard. Every request is checked here on the server; the screen only mirrors it.

Access comes from the first of: being the owner, a share made to the person (by account or email), or a share made to a contact group the
person belongs to. Group access follows the group as it is now: add someone to the group and they get access, remove them and it ends.
Opening a link makes a personal share for the person who opened it, so revoking the link also ends what it granted."""
import hashlib, secrets
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User, Note, NoteShare, Contact, ContactGroup

RANK = {"viewer": 1, "commenter": 2, "editor": 3, "owner": 4}
GRANTABLE = ("viewer", "commenter", "editor")        # owner is never given through sharing
NAMES = {1: "viewer", 2: "commenter", 3: "editor", 4: "owner"}

def new_secret() -> str: return secrets.token_urlsafe(32)
def digest(secret: str) -> str: return hashlib.sha256(secret.encode()).hexdigest()
def now() -> datetime: return datetime.now(timezone.utc)
def aware(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)
def live(r: NoteShare) -> bool:
    return r.revoked_at is None and (r.expires_at is None or aware(r.expires_at) > now())
def status(r: NoteShare) -> str:
    return "revoked" if r.revoked_at else "expired" if r.expires_at and aware(r.expires_at) <= now() else "active"

async def group_emails(db: AsyncSession, g: ContactGroup | None, owner_id: str) -> list[tuple[str, str]]:
    """(name, email) of everyone now in the group; only the owner's own contacts can be members."""
    if not g or g.owner_id != owner_id or not (g.contact_ids or []): return []
    rows = (await db.execute(select(Contact).where(Contact.owner_id == owner_id, Contact.id.in_(g.contact_ids)))).scalars().all()
    return [(c.name, c.email.strip().lower()) for c in rows if c.email and "@" in c.email]

async def share_applies(db: AsyncSession, r: NoteShare, user: User, owner_id: str) -> bool:
    em = (user.email or "").strip().lower()
    if r.kind == "user": return (r.user_id == user.id) or bool(r.email and r.email == em)
    if r.kind == "group": return any(e == em for _, e in await group_emails(db, await db.get(ContactGroup, r.group_id) if r.group_id else None, owner_id))
    return False                                                       # a link grants nothing until someone opens it

async def access_level(db: AsyncSession, user: User, note: Note) -> int:
    """0 none, 1 viewer, 2 commenter, 3 editor, 4 owner."""
    if note.owner_id == user.id: return 4
    best = 0
    for r in (await db.execute(select(NoteShare).where(NoteShare.note_id == note.id, NoteShare.kind.in_(("user", "group"))))).scalars().all():
        if live(r) and RANK.get(r.permission, 0) > best and await share_applies(db, r, user, note.owner_id): best = RANK[r.permission]
    return best

def name_of(u: User | None) -> str: return ((u.display_name or u.email) if u else "").strip()
