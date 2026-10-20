"""Sharing notes and whiteboards: people, contact groups and secret links, with Viewer / Commenter / Editor access enforced on the server,
an email invitation (a link, never the content), in-app alerts, and the Shared with me / Shared by me lists. Comments live here too."""
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal
from app.models import User, Contact, ContactGroup, Note, NoteShare, NoteComment
from app.services import sharing as sh, notify
from app.services.invites import EMAIL
from app.services.identity import shown_email

router = APIRouter(prefix="/api/v1", tags=["sharing"])

def _utc(d) -> str | None:
    return None if d is None else sh.aware(d).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

async def _owned(db: AsyncSession, user: User, nid: str) -> Note:
    n = await db.get(Note, nid)
    if not n or n.owner_id != user.id: raise HTTPException(404, "Not found")
    return n

def _perm(p) -> str:
    p = str(p or "viewer").lower()
    if p == "owner": raise HTTPException(400, "Owner access cannot be given by sharing.")
    if p not in sh.GRANTABLE: raise HTTPException(400, "Choose Viewer, Commenter or Editor.")
    return p

def _expiry(v) -> datetime | None:
    if not v: return None
    try: d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError: raise HTTPException(400, "That expiry date is not valid.")
    d = sh.aware(d)
    if d <= sh.now(): raise HTTPException(400, "The expiry must be in the future.")
    return d

def _base(payload: dict) -> str:
    """Where invitation links point. Only the app's own address is accepted, so a forged request cannot make our email point somewhere else."""
    own = urlparse(settings.frontend_origin); b = str(payload.get("base_url") or "")
    u = urlparse(b)
    if u.scheme in ("http", "https") and u.netloc and (u.netloc == own.netloc or settings.frontend_origin.startswith("http://localhost")): return f"{u.scheme}://{u.netloc}{u.path or '/'}"
    return settings.frontend_origin.rstrip("/") + "/"

def _link(base: str, secret: str) -> str: return f"{base}#/shared/{secret}"
async def _user_by_email(db, email: str) -> User | None:
    return (await db.execute(select(User).where(func.lower(User.email) == email.lower(), User.is_active == True))).scalars().first()  # noqa: E712
def _what(n: Note) -> str: return "whiteboard" if n.kind == "board" else "note"

async def _alert(db, to: User | None, kind, title, text, url="", sender=""):
    if to:
        try: await notify.notify(db, to.email, kind, title, text, url, sender)
        except Exception: pass

async def _mail_invite(db, owner: User, n: Note, to_email: str, to_name: str, perm: str, message: str, link: str, expires, results_for: dict) -> None:
    from app.integrations import mail as mailer
    from app.api.routes_booking import _senders
    senders = await _senders(db, owner)
    if not senders: results_for.update(emailed=False, error="No email account is set up to send from."); return
    me = sh.name_of(owner)
    body = (f"Hello{(' ' + to_name.split()[0]) if to_name else ''},\n\n{me} has shared the {_what(n)} \"{n.title}\" with you. You have been granted {perm.capitalize()} access.\n"
            + (f"\n{message}\n" if message else "") + f"\nOpen it using the secure link below (you will be asked to sign in to iSift):\n{link}\n"
            + (f"\nThis access expires on {sh.aware(expires).strftime('%d %b %Y')}.\n" if expires else "") + "\nThe link only works for the person it was sent to. Sent with iSift.")
    for acct in senders:
        try: await mailer.send(acct, [to_email], f"{me} shared a {_what(n)} with you: {n.title}", body); results_for.update(emailed=True); return
        except Exception: continue
    results_for.update(emailed=False, error="The email could not be sent.")

@router.post("/notes/{nid}/shares")
async def add_shares(nid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Share with people (typed emails, contacts) and contact groups. Sharing again with someone who already has access changes their level and does not send a second invitation."""
    n = await _owned(db, user, nid); perm = _perm(payload.get("permission")); exp = _expiry(payload.get("expires_at"))
    msg = str(payload.get("message") or "").strip()[:2000]; send = payload.get("send_email", True) is not False; base = _base(payload)
    people: dict[str, str] = {}
    for e in payload.get("emails") or []:
        e = str(e).strip().lower()
        if not e: continue
        if not EMAIL.match(e): raise HTTPException(400, f"'{e}' is not a valid email address.")
        people[e] = ""
    cids = {str(i) for i in payload.get("contact_ids") or []}
    if cids:
        for c in (await db.execute(select(Contact).where(Contact.owner_id == user.id, Contact.id.in_(cids)))).scalars().all():
            if c.email and EMAIL.match(c.email.strip()): people.setdefault(c.email.strip().lower(), c.name)
    groups = []
    for gid in payload.get("group_ids") or []:
        g = await db.get(ContactGroup, str(gid))
        if g and g.owner_id == user.id: groups.append(g)
    if not people and not groups: raise HTTPException(400, "Choose at least one person, group or email address.")
    if len(people) + len(groups) > 50: raise HTTPException(400, "You can share with up to 50 people or groups at a time.")
    me = user.email.lower(); results = []
    existing = (await db.execute(select(NoteShare).where(NoteShare.note_id == n.id, NoteShare.kind.in_(("user", "group")), NoteShare.revoked_at.is_(None), NoteShare.via_link.is_(None)))).scalars().all()
    async def invite(r: NoteShare, secret: str, to_email: str, to_name: str, res: dict):
        target = await _user_by_email(db, to_email)
        await _alert(db, target, "share", f"{sh.name_of(user)} shared a {_what(n)} with you", f"{n.title} · {perm.capitalize()} access", _link(base, secret), sh.name_of(user))
        if send: await _mail_invite(db, user, n, to_email, to_name, perm, msg, _link(base, secret), exp, res)
        else: res["emailed"] = None
    for em, nm in people.items():
        if em == me: results.append({"to": em, "status": "skipped", "error": "That is you; you already own it."}); continue
        target = await _user_by_email(db, em); r = next((x for x in existing if x.kind == "user" and ((target and x.user_id == target.id) or x.email == em)), None); res = {"to": em, "name": nm}
        if r:
            if r.permission == perm and (sh.aware(r.expires_at) == exp): res["status"] = "unchanged"
            else:
                changed = r.permission != perm; r.permission = perm; r.expires_at = exp; res["status"] = "updated"
                if changed: await _alert(db, target, "share_changed", f"Your access to \"{n.title}\" changed", f"You now have {perm.capitalize()} access.", "", sh.name_of(user))
        else:
            secret = sh.new_secret(); r = NoteShare(note_id=n.id, kind="user", user_id=target.id if target else None, email=em, permission=perm, token_hash=sh.digest(secret), message=msg, created_by=user.id, expires_at=exp)
            db.add(r); await db.flush(); res["status"] = "shared"; await invite(r, secret, em, nm, res)
        results.append(res)
    for g in groups:
        members = await sh.group_emails(db, g, user.id); r = next((x for x in existing if x.kind == "group" and x.group_id == g.id), None); res = {"to": g.name, "group": True, "members": len(members)}
        if not members: res.update(status="skipped", error="That group has no members with an email address."); results.append(res); continue
        if r:
            changed = r.permission != perm; r.permission = perm; r.expires_at = exp; res["status"] = "updated" if changed else "unchanged"
            if changed:
                for _, e in members: await _alert(db, await _user_by_email(db, e), "share_changed", f"Your access to \"{n.title}\" changed", f"You now have {perm.capitalize()} access.", "", sh.name_of(user))
        else:
            secret = sh.new_secret(); r = NoteShare(note_id=n.id, kind="group", group_id=g.id, permission=perm, token_hash=sh.digest(secret), message=msg, created_by=user.id, expires_at=exp)
            db.add(r); await db.flush(); res["status"] = "shared"; sent = failed = 0
            for nm, e in members:
                if e == me: continue
                one: dict = {}; await invite(r, secret, e, nm, one)
                if one.get("emailed") is False: failed += 1
                elif one.get("emailed"): sent += 1
            res.update(emailed_count=sent, failed_count=failed, emailed=(None if not send else failed == 0 and sent > 0))
            if send and failed: res["error"] = f"{failed} member(s) could not be emailed."
        results.append(res)
    await db.commit()
    from app.api.routes_booking import _senders
    return {"results": results, "email_configured": bool(await _senders(db, user))}

async def _who(db, r: NoteShare, owner_id: str) -> dict:
    d = {"id": r.id, "kind": r.kind, "permission": r.permission, "status": sh.status(r), "created_at": _utc(r.created_at), "expires_at": _utc(r.expires_at)}
    if r.kind == "group":
        g = await db.get(ContactGroup, r.group_id) if r.group_id else None
        d.update(name=g.name if g else "(deleted group)", members=[{"name": a, "email": b} for a, b in await sh.group_emails(db, g, owner_id)])
    elif r.kind == "link":
        d.update(name="Anyone signed in with the link", restricted=bool(r.restrict_emails), emails=r.restrict_emails or [], opened_by=(await db.execute(select(func.count()).select_from(NoteShare).where(NoteShare.via_link == r.id, NoteShare.revoked_at.is_(None)))).scalar() or 0)
    else:
        u = await db.get(User, r.user_id) if r.user_id else await _user_by_email(db, r.email)
        d.update(name=(sh.name_of(u) if u else r.email), email=(u.email if u else r.email), has_account=bool(u))
    return d

@router.get("/notes/{nid}/shares")
async def list_shares(nid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n = await _owned(db, user, nid)
    rows = (await db.execute(select(NoteShare).where(NoteShare.note_id == n.id, NoteShare.revoked_at.is_(None)).order_by(NoteShare.created_at))).scalars().all()
    people = [await _who(db, r, n.owner_id) for r in rows if r.kind != "link" and not r.via_link]
    opened = [await _who(db, r, n.owner_id) for r in rows if r.via_link]
    return {"people": people, "links": [await _who(db, r, n.owner_id) for r in rows if r.kind == "link"], "opened_from_links": len(opened)}

async def _row(db, n: Note, sid: str) -> NoteShare:
    r = await db.get(NoteShare, sid)
    if not r or r.note_id != n.id or r.revoked_at: raise HTTPException(404, "Not found")
    return r

async def _affected(db, r: NoteShare, owner_id: str) -> list[User]:
    if r.kind == "user": return [u for u in [(await db.get(User, r.user_id)) if r.user_id else await _user_by_email(db, r.email)] if u]
    if r.kind == "group": return [u for u in [await _user_by_email(db, e) for _, e in await sh.group_emails(db, await db.get(ContactGroup, r.group_id), owner_id)] if u]
    return []

@router.patch("/notes/{nid}/shares/{sid}")
async def change_share(nid: str, sid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n = await _owned(db, user, nid); r = await _row(db, n, sid)
    if "permission" in payload:
        p = _perm(payload["permission"]); changed = p != r.permission; r.permission = p
        if r.kind == "link":                                                      # people who already opened the link follow its new level
            for x in (await db.execute(select(NoteShare).where(NoteShare.via_link == r.id, NoteShare.revoked_at.is_(None)))).scalars().all(): x.permission = p
        elif changed:
            for u in await _affected(db, r, n.owner_id): await _alert(db, u, "share_changed", f"Your access to \"{n.title}\" changed", f"You now have {p.capitalize()} access.", "", sh.name_of(user))
    if "expires_at" in payload:
        r.expires_at = _expiry(payload["expires_at"])
        if r.kind == "link":
            for x in (await db.execute(select(NoteShare).where(NoteShare.via_link == r.id, NoteShare.revoked_at.is_(None)))).scalars().all(): x.expires_at = r.expires_at
    await db.commit(); return await _who(db, r, n.owner_id)

@router.delete("/notes/{nid}/shares/{sid}")
async def revoke_share(nid: str, sid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Withdraw a person's, a group's or a link's access straight away. For a link this also ends the access of everyone who opened it."""
    n = await _owned(db, user, nid); r = await _row(db, n, sid); t = sh.now(); r.revoked_at = t; gone = await _affected(db, r, n.owner_id)
    if r.kind == "link":
        for x in (await db.execute(select(NoteShare).where(NoteShare.via_link == r.id, NoteShare.revoked_at.is_(None)))).scalars().all():
            x.revoked_at = t; gone += await _affected(db, x, n.owner_id)
    for u in gone: await _alert(db, u, "share_revoked", f"Access to \"{n.title}\" was removed", f"{sh.name_of(user)} stopped sharing it with you.", "", sh.name_of(user))
    await db.commit(); return {"ok": True}

@router.post("/notes/{nid}/stop-sharing")
async def stop_sharing(nid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n = await _owned(db, user, nid); rows = (await db.execute(select(NoteShare).where(NoteShare.note_id == n.id, NoteShare.revoked_at.is_(None)))).scalars().all(); t = sh.now(); gone = []
    for r in rows: r.revoked_at = t; gone += await _affected(db, r, n.owner_id)
    for u in {u.id: u for u in gone}.values(): await _alert(db, u, "share_revoked", f"Access to \"{n.title}\" was removed", f"{sh.name_of(user)} stopped sharing it with you.", "", sh.name_of(user))
    await db.commit(); return {"ok": True, "removed": len(rows)}

@router.post("/notes/{nid}/links")
async def make_link(nid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """A secret link. It works only for signed-in people (optionally only for named addresses), until its expiry, or until it is revoked. The link is shown once; only a hash is kept."""
    n = await _owned(db, user, nid); perm = _perm(payload.get("permission")); exp = _expiry(payload.get("expires_at"))
    only = []
    for e in payload.get("emails") or []:
        e = str(e).strip().lower()
        if e and not EMAIL.match(e): raise HTTPException(400, f"'{e}' is not a valid email address.")
        if e: only.append(e)
    secret = sh.new_secret(); r = NoteShare(note_id=n.id, kind="link", permission=perm, token_hash=sh.digest(secret), restrict_emails=only, created_by=user.id, expires_at=exp)
    db.add(r); await db.commit()
    return {"id": r.id, "url": _link(_base(payload), secret), "permission": perm, "expires_at": _utc(exp), "restricted": bool(only)}

@router.post("/shared/open")
async def open_shared(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    secret = str(payload.get("token") or "").strip()
    r = (await db.execute(select(NoteShare).where(NoteShare.token_hash == sh.digest(secret)))).scalars().first() if secret else None
    n = await db.get(Note, r.note_id) if r else None
    if not r or not n: raise HTTPException(404, "This link is not valid.")
    if not sh.live(r): raise HTTPException(410, "This link has expired or the owner has withdrawn it.")
    if n.owner_id == user.id: return {"id": n.id, "kind": n.kind, "title": n.title, "access": "owner"}
    em = (user.email or "").lower()
    if r.kind == "link":
        if r.restrict_emails and em not in r.restrict_emails and await sh.access_level(db, user, n) == 0: raise HTTPException(403, "This link was made for specific people and your address is not one of them.")
        mine = (await db.execute(select(NoteShare).where(NoteShare.note_id == n.id, NoteShare.via_link == r.id, NoteShare.user_id == user.id, NoteShare.revoked_at.is_(None)))).scalars().first()
        if mine: mine.permission = r.permission; mine.expires_at = r.expires_at
        else:
            db.add(NoteShare(note_id=n.id, kind="user", user_id=user.id, email=em, permission=r.permission, via_link=r.id, created_by=n.owner_id, expires_at=r.expires_at))
            await _alert(db, await db.get(User, n.owner_id), "share_opened", f"{sh.name_of(user)} opened your link", f"{n.title}", "", sh.name_of(user))
        await db.commit()
    elif not await sh.share_applies(db, r, user, n.owner_id): raise HTTPException(403, "This invitation was sent to a different person. Sign in with the address it was sent to.")
    lvl = await sh.access_level(db, user, n)
    if not lvl: raise HTTPException(403, "You do not have access to this.")
    return {"id": n.id, "kind": n.kind, "title": n.title, "access": sh.NAMES[lvl]}

@router.get("/shared/with-me")
async def shared_with_me(kind: str = "", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    em = (user.email or "").lower(); cand: dict[str, list[NoteShare]] = {}
    for r in (await db.execute(select(NoteShare).where(NoteShare.kind == "user", NoteShare.revoked_at.is_(None), (NoteShare.user_id == user.id) | (NoteShare.email == em)))).scalars().all(): cand.setdefault(r.note_id, []).append(r)
    mine = (await db.execute(select(Contact).where(func.lower(Contact.email) == em))).scalars().all()
    if mine:
        gids = [g.id for g in (await db.execute(select(ContactGroup).where(ContactGroup.owner_id.in_({c.owner_id for c in mine})))).scalars().all() if any(c.id in (g.contact_ids or []) and c.owner_id == g.owner_id for c in mine)]
        if gids:
            for r in (await db.execute(select(NoteShare).where(NoteShare.kind == "group", NoteShare.revoked_at.is_(None), NoteShare.group_id.in_(gids)))).scalars().all(): cand.setdefault(r.note_id, []).append(r)
    out = []
    for nid, rows in cand.items():
        n = await db.get(Note, nid)
        if not n or n.owner_id == user.id or (kind and n.kind != kind): continue
        rows = [r for r in rows if sh.live(r)]
        if not rows: continue
        best = max(rows, key=lambda r: sh.RANK.get(r.permission, 0)); owner = await db.get(User, n.owner_id)
        out.append({"id": n.id, "kind": n.kind, "title": n.title, "owner": sh.name_of(owner), "owner_email": shown_email(owner.email) if owner else "", "access": best.permission, "shared_at": _utc(max(r.created_at for r in rows)),
                    "updated_at": _utc(n.updated_at), "expires_at": _utc(best.expires_at), "via": "group" if best.kind == "group" else "link" if best.via_link else "direct", "status": "active"})
    out.sort(key=lambda x: x["shared_at"] or "", reverse=True); return out

@router.get("/shared/by-me")
async def shared_by_me(kind: str = "", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    q = select(Note).where(Note.owner_id == user.id)
    if kind: q = q.where(Note.kind == kind)
    out = []
    for n in (await db.execute(q.order_by(Note.updated_at.desc()))).scalars().all():
        rows = [r for r in (await db.execute(select(NoteShare).where(NoteShare.note_id == n.id, NoteShare.revoked_at.is_(None)))).scalars().all() if not r.via_link]
        if not rows: continue
        names = []
        for r in rows:
            if r.kind == "link": continue
            names.append((await _who(db, r, n.owner_id))["name"])
        links = [r for r in rows if r.kind == "link"]
        out.append({"id": n.id, "kind": n.kind, "title": n.title, "recipients": names, "links": [{"id": r.id, "permission": r.permission, "status": sh.status(r), "expires_at": _utc(r.expires_at)} for r in links],
                    "shared_at": _utc(max(r.created_at for r in rows)), "updated_at": _utc(n.updated_at), "status": "active" if any(sh.live(r) for r in rows) else "expired"})
    return out

# ---------------- comments ----------------
async def _can(db, user, nid, need: int) -> tuple[Note, int]:
    n = await db.get(Note, nid); lvl = await sh.access_level(db, user, n) if n else 0
    if not lvl: raise HTTPException(404, "Not found")
    if lvl < need: raise HTTPException(403, "Your access does not allow that.")
    return n, lvl

def _c(c: NoteComment, me: str, lvl: int) -> dict:
    return {"id": c.id, "author": c.author, "text": c.text, "at": _utc(c.created_at), "mine": c.user_id == me, "can_delete": c.user_id == me or lvl == 4}

@router.get("/notes/{nid}/comments")
async def comments(nid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n, lvl = await _can(db, user, nid, 1)
    rows = (await db.execute(select(NoteComment).where(NoteComment.note_id == n.id).order_by(NoteComment.created_at))).scalars().all()
    return {"items": [_c(c, user.id, lvl) for c in rows], "can_comment": lvl >= 2}

@router.post("/notes/{nid}/comments")
async def add_comment(nid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n, lvl = await _can(db, user, nid, 2); text = str(payload.get("text") or "").strip()[:2000]
    if not text: raise HTTPException(400, "Write a comment first.")
    c = NoteComment(note_id=n.id, user_id=user.id, author=sh.name_of(user), text=text); db.add(c); await db.commit()
    if n.owner_id != user.id: await _alert(db, await db.get(User, n.owner_id), "comment", f"{sh.name_of(user)} commented on \"{n.title}\"", text[:140], "", sh.name_of(user))
    return _c(c, user.id, lvl)

@router.delete("/notes/{nid}/comments/{cid}")
async def delete_comment(nid: str, cid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n, lvl = await _can(db, user, nid, 1); c = await db.get(NoteComment, cid)
    if not c or c.note_id != n.id: raise HTTPException(404, "Not found")
    if c.user_id != user.id and lvl < 4: raise HTTPException(403, "Only the author or the owner can delete a comment.")
    await db.delete(c); await db.commit(); return {"ok": True}
