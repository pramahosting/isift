"""Connections: calendar links (Google, Yahoo, Outlook.com, iCloud), Zoom, and creating meetings."""
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal, require_admin
from app.core import runtime_settings as rs
from app.core.config import settings
from app.models import User, Meeting, AuditLog, IntegrationSetting
from app.services import calendar_sync as cal
from app.integrations import ics_feed, zoom, caldav, google, mail as mailer
from app.integrations.graph import GraphUnavailable, GraphClient, mailbox_for

router = APIRouter(prefix="/api/v1")

def _public_feed(it: dict) -> dict:
    host = ""
    try: host = urlsplit(rs._dec(it["url"])).hostname or ""
    except Exception: pass
    return {"id": it["id"], "provider": it["provider"], "kind": it.get("kind", "ics"), "label": it.get("label") or (caldav.PRESETS if it.get("kind") == "caldav" else ics_feed.PROVIDERS).get(it["provider"], {}).get("label", "Calendar"),
            "host": host, "ok": it.get("ok"), "error": it.get("error"), "at": it.get("at")}

async def _mail_public(db, user):
    m = await cal.get_mail(db, user.id)
    if not m: return None
    return {"provider": m.get("provider"), "address": m.get("address"), "import_invites": bool(m.get("import_invites")), "ok": m.get("ok"), "error": m.get("error"), "at": m.get("at")}

@router.get("/connections")
async def connections(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    return {"providers": [{"id": k, **v} for k, v in ics_feed.PROVIDERS.items()],
            "caldav_presets": [{"id": k, **v} for k, v in caldav.PRESETS.items()],
            "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)],
            "uploaded": bool(await cal.get_upload(db, user.id)),
            "computer": await cal.machine_status(db, user.id, True),
            "mail_presets": [{"id": k, "label": v["label"], "how": v["how"], "smtp_host": v["smtp"][0], "smtp_port": v["smtp"][1], "imap_host": v["imap"][0], "imap_port": v["imap"][1]} for k, v in mailer.PRESETS.items()],
            "mail": await _mail_public(db, user),
            "zoom": {"configured": zoom.configured()},
            "microsoft": {"configured": cal.graph_configured()},
            "outlook": await _outlook_public(db, user)}

def _outlook_key(user_id: str) -> str:
    return f"outlook_pull:{user_id}"

async def _outlook_public(db: AsyncSession, user: User) -> dict:
    await rs.apply_overrides(db)
    row = await db.get(IntegrationSetting, _outlook_key(user.id)); v = (row.value if row else None) or {}
    cid = settings.ms_signin_client_id
    return {"ready": bool(cid), "client_id": cid or "", "authority": f"https://login.microsoftonline.com/{settings.entra_tenant_id or 'common'}",
            "connected": bool(v), "account": v.get("account"), "name": v.get("name"), "at": v.get("at"), "meetings": v.get("meetings", 0), "mail_count": len(v.get("mail", [])),
            "mail": [{k: m.get(k) for k in ("subject", "from", "at", "read")} for m in v.get("mail", [])[:10]]}

@router.post("/connections/microsoft/pull")
async def outlook_pull(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """The browser signed the person in to Microsoft (popup) and passes the short-lived access token. Pull their calendar and
    recent email once. The token is used for this request only and is never stored."""
    from app.integrations import graph as g
    token = str(payload.get("access_token") or "").strip()
    if len(token) < 20: raise HTTPException(422, "Sign in to Microsoft first.")
    tz = await cal.user_timezone(db); start, _ = cal.today_window(tz); end = start + timedelta(days=30)
    try:
        prof = await g.me_profile(token)
        events = await g.me_calendar(token, start, end)
        mail = await g.me_mail(token, 50) if payload.get("mail", True) else []
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    contacts_note = ""
    try:
        from app.api.routes_workspace import import_contacts
        cr = await import_contacts(db, user, await g.me_contacts(token), prof["email"])
        contacts_note = f" Contacts: {cr['added']} added, {cr['skipped']} already there."
    except GraphUnavailable: contacts_note = " Contacts could not be read (sign in again and accept the contacts permission)."
    res = await cal.apply_events(db, user.id, events, start, end, "outlook", mark_stale=False, account=prof["email"])
    row = await db.get(IntegrationSetting, _outlook_key(user.id))
    val = {"account": prof["email"], "name": prof["name"], "at": datetime.now(timezone.utc).isoformat(), "meetings": res["eligible"], "mail": mail}
    if row: row.value = val
    else: db.add(IntegrationSetting(key=_outlook_key(user.id), value=val))
    db.add(AuditLog(actor=user.email, action="outlook.pull", resource_type="calendar", safe_metadata={"meetings": res["eligible"], "mail": len(mail)})); await db.commit()
    return {"ok": True, "account": prof["email"], "message": f"Signed in as {prof['email']}. Added {res['added']} and updated {res['updated']} meetings ({res['eligible']} in the next 30 days) and read {len(mail)} recent emails." + contacts_note}

@router.post("/connections/outlook-desktop/pull")
async def outlook_desktop_pull(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Read the classic Outlook program on this Windows computer: calendar (next 30 days), recent email and contacts. No sign-in needed."""
    from app.integrations import machine_calendar as mc
    from app.api.routes_workspace import import_contacts
    tz = await cal.user_timezone(db); start, _ = cal.today_window(tz); end = start + timedelta(days=30)
    try:
        events = await mc._outlook_events(start, end)
        people = await mc.outlook_people()
    except mc.MachineCalendarError as exc: raise HTTPException(502, str(exc))
    acc = people["account"] or "Outlook on this computer"
    res = await cal.apply_events(db, user.id, events, start, end, "outlook", mark_stale=False, account=acc)
    cr = await import_contacts(db, user, people["contacts"], acc)
    mail = [{"subject": (m.get("subject") or "(no subject)")[:200], "from": m.get("from") or "", "at": m.get("at"), "preview": (m.get("preview") or "")[:240], "read": bool(m.get("read"))} for m in people["mail"]]
    val = {"account": people["account"] or "Outlook on this computer", "name": "", "at": datetime.now(timezone.utc).isoformat(), "meetings": res["eligible"], "mail": mail}
    row = await db.get(IntegrationSetting, _outlook_key(user.id))
    if row: row.value = val
    else: db.add(IntegrationSetting(key=_outlook_key(user.id), value=val))
    db.add(AuditLog(actor=user.email, action="outlook.desktop.pull", resource_type="calendar", safe_metadata={"meetings": res["eligible"], "mail": len(mail), "contacts": cr["added"]})); await db.commit()
    return {"ok": True, "message": f"Read Outlook on this computer: {res['eligible']} meetings in the next 30 days, {len(mail)} recent emails, {cr['added']} new contacts ({cr['skipped']} already there)."}

@router.get("/connections/microsoft/mail")
async def outlook_mail(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """The recent email pulled from Outlook for this person (summaries only), newest first."""
    row = await db.get(IntegrationSetting, _outlook_key(user.id)); v = (row.value if row else None) or {}
    return {"connected": bool(v), "account": v.get("account"), "at": v.get("at"), "mail": v.get("mail", [])}

@router.delete("/connections/microsoft/outlook")
async def outlook_forget(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Forget the stored email summaries for this person. Meetings already added stay."""
    row = await db.get(IntegrationSetting, _outlook_key(user.id))
    if row: await db.delete(row); await db.commit()
    return {"ok": True, "message": "Outlook email summaries removed. Meetings already added stay."}

@router.post("/connections/calendar-links")
async def add_link(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    provider = payload.get("provider") if payload.get("provider") in ics_feed.PROVIDERS else "other"
    url = str(payload.get("url") or "").strip()
    if not url: raise HTTPException(422, "Paste the calendar link first.")
    items = await cal.get_feeds(db, user.id)
    if len(items) >= 10: raise HTTPException(422, "You can add up to 10 calendar links. Remove one first.")
    try: text = await ics_feed.fetch_text(url)          # test it before saving
    except ics_feed.FeedError as exc: raise HTTPException(422, str(exc))
    tz = await cal.user_timezone(db); start, _ = cal.today_window(tz)
    n = len(cal.machine.events_from_ics_text(text, start, start + timedelta(days=cal.DAYS_AHEAD + 1)))
    items.append({"id": uuid.uuid4().hex[:12], "provider": provider, "label": str(payload.get("label") or "")[:80], "url": rs._enc(ics_feed.normalize(url)), "ok": True, "error": None, "at": datetime.now(timezone.utc).isoformat()})
    await cal.save_feeds(db, user.id, items)
    db.add(AuditLog(actor=user.email, action="calendar.link.add", resource_type="calendar", safe_metadata={"provider": provider})); await db.commit()
    try: result = await cal.sync_calendar(db, user.id)
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Calendar connected: {n} event(s) in the next {cal.DAYS_AHEAD} days, {result['added']} new meeting(s) added.", "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)]}

@router.post("/connections/caldav")
async def add_caldav(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    preset = payload.get("provider") if payload.get("provider") in caldav.PRESETS else "other"
    url = str(payload.get("url") or caldav.PRESETS[preset]["url"]).strip()
    username = str(payload.get("username") or "").strip(); password = str(payload.get("password") or "")
    if not url or not username or not password: raise HTTPException(422, "Enter the server address, username and app password.")
    items = await cal.get_feeds(db, user.id)
    if len(items) >= 10: raise HTTPException(422, "You can add up to 10 calendars. Remove one first.")
    tz = await cal.user_timezone(db); start, _ = cal.today_window(tz); end = start + timedelta(days=cal.DAYS_AHEAD + 1)
    try:
        text = await caldav.fetch_text(url, username, password, start, end)     # test before saving
    except (caldav.CalDavError, ics_feed.FeedError) as exc: raise HTTPException(422, str(exc))
    n = len(cal.machine.events_from_ics_text(text, start, end))
    items.append({"id": uuid.uuid4().hex[:12], "kind": "caldav", "provider": preset, "label": str(payload.get("label") or "")[:80], "url": rs._enc(url), "username": rs._enc(username),
                  "password": rs._enc(password), "ok": True, "error": None, "at": datetime.now(timezone.utc).isoformat()})
    await cal.save_feeds(db, user.id, items)
    db.add(AuditLog(actor=user.email, action="calendar.caldav.add", resource_type="calendar", safe_metadata={"provider": preset})); await db.commit()
    try: result = await cal.sync_calendar(db, user.id)
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Calendar connected: {n} event(s) in the next {cal.DAYS_AHEAD} days, {result['added']} new meeting(s) added.", "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)]}

@router.delete("/connections/calendar-links/{link_id}")
async def remove_link(link_id: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    items = await cal.get_feeds(db, user.id)
    keep = [i for i in items if i["id"] != link_id]
    if len(keep) == len(items): raise HTTPException(404, "Calendar link not found")
    await cal.save_feeds(db, user.id, keep)
    db.add(AuditLog(actor=user.email, action="calendar.link.remove", resource_type="calendar", safe_metadata={})); await db.commit()
    return {"links": [_public_feed(i) for i in keep]}

@router.post("/connections/sync")
async def sync_now(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    try: result = await cal.sync_calendar(db, user.id)
    except GraphUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Calendar refreshed: {result['eligible']} meeting(s), {result['added']} new.", "links": [_public_feed(i) for i in await cal.get_feeds(db, user.id)]}

PLATFORM_NAMES = {"zoom": "Zoom", "teams": "Microsoft Teams", "meet": "Google Meet"}

@router.get("/meeting-platforms")
async def platforms(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Which meeting platforms can book for this person right now (checked from Admin settings)."""
    await rs.apply_overrides(db)
    teams_ok = cal.graph_configured() and bool(mailbox_for(user.email))
    meet_ok = google.configured() and bool(google.subject_for(user.email))
    teams_why = "" if teams_ok else ("Add the Microsoft client ID, secret and tenant ID in Admin settings." if not cal.graph_configured() else "Set the Microsoft calendar user in Admin settings.")
    meet_why = "" if meet_ok else ("Add the Google service account key in Admin settings." if not google.configured() else "Set the Google calendar user in Admin settings.")
    return {"isift": {"ready": True}, "zoom": {"ready": zoom.configured(), "why": "" if zoom.configured() else "Add the Zoom account ID, client ID and client secret in Admin settings."},
            "teams": {"ready": teams_ok, "why": teams_why}, "meet": {"ready": meet_ok, "why": meet_why}, "is_admin": user.role == "admin"}

@router.post("/connections/zoom/test")
async def zoom_test(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await rs.apply_overrides(db)
    try: info = await zoom.ping()
    except zoom.ZoomUnavailable as exc: raise HTTPException(502, str(exc))
    return {"message": f"Zoom is connected ({info.get('email') or 'account ok'})."}

@router.post("/meetings")
async def create_meeting(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Schedule a meeting. With provider 'zoom' (and Zoom set up) a real Zoom meeting is created and its join link stored."""
    title = str(payload.get("title") or "").strip()[:200]
    if not title: raise HTTPException(422, "Give the meeting a title.")
    try: start = datetime.fromisoformat(str(payload.get("start_at")).replace("Z", "+00:00"))
    except ValueError: raise HTTPException(422, "Choose a valid start date and time.")
    tz = _pick_zone(payload, await cal.user_timezone(db))
    if start.tzinfo is None: start = start.replace(tzinfo=tz)
    minutes = int(payload.get("duration_minutes") or 30)
    if not 5 <= minutes <= 720: raise HTTPException(422, "Duration must be between 5 minutes and 12 hours.")
    agenda = str(payload.get("agenda") or "")[:2000]
    join, ext = None, f"local:{uuid.uuid4().hex}"
    if payload.get("provider") == "zoom":
        await rs.apply_overrides(db)
        try: z = await zoom.create_meeting(title, start, minutes, str(tz), "me" if user.email == "admin@example.test" else user.email, agenda)
        except zoom.ZoomUnavailable as exc: raise HTTPException(502, str(exc))
        join, ext = z["join_url"], f"zoom:{z['id']}"
    elif payload.get("provider") in ("teams", "meet"):
        await rs.apply_overrides(db)
        plat = payload["provider"]; end = start + timedelta(minutes=minutes)
        try:
            if plat == "teams":
                mb = mailbox_for(user.email)
                if not (cal.graph_configured() and mb): raise HTTPException(409, "Microsoft Teams is not set up yet. An administrator can add it in Admin settings > Meeting platforms.")
                z = await GraphClient().create_teams_meeting(mb, title, start, end, agenda)
            else:
                sub = google.subject_for(user.email)
                if not (google.configured() and sub): raise HTTPException(409, "Google Meet is not set up yet. An administrator can add it in Admin settings > Meeting platforms.")
                z = await google.create_meet(sub, title, start, end, str(tz), agenda)
        except (GraphUnavailable, google.GoogleUnavailable) as exc: raise HTTPException(502, str(exc))
        join, ext = z["join_url"], f"{plat}:{z['id']}"
    elif payload.get("provider") == "room":
        from app.api.routes_rooms import make_room
        from app.api.routes_workspace import get_pmi, set_pmi_open
        times = _series(start, payload.get("recurrence")); start = times[0]; span = timedelta(minutes=minutes)
        recurring = len(times) > 1; use_pmi = payload.get("meeting_id_mode") == "personal"
        shared = recurring or use_pmi
        m0 = Meeting(owner_id=user.id, external_id=f"local:{uuid.uuid4().hex}", title=title, organizer=user.email, start_at=start.astimezone(timezone.utc), end_at=(start + span).astimezone(timezone.utc), sensitivity="normal", status="scheduled")
        db.add(m0); await db.flush()
        opts = dict(payload.get("options") or {})
        if str(payload.get("invite") or "").strip():
            from app.services.invites import parse_recipients
            try: opts["invitees"] = parse_recipients(str(payload["invite"]))
            except ValueError as exc: raise HTTPException(422, str(exc))
        m0.agenda = agenda or None
        if use_pmi:
            from app.api.routes_rooms import room_url
            room = await get_pmi(db, user)
            if "open_room" in opts: await set_pmi_open(db, room, bool(opts["open_room"]))
            m0.join_url = room_url(str(payload.get("base_url") or ""), room.code)
        else:
            room, m0 = await make_room(db, user, title, str(payload.get("base_url") or ""), meeting=m0, access=payload.get("access"), passcode=payload.get("passcode"), waiting_room=payload.get("waiting_room"), options=opts)
        m0.external_id = f"room:{room.code}#{uuid.uuid4().hex[:8]}" if shared else f"room:{room.code}"
        for t in times[1:]:
            db.add(Meeting(owner_id=user.id, external_id=f"room:{room.code}#{uuid.uuid4().hex[:8]}", title=title, organizer=user.email, start_at=t.astimezone(timezone.utc), end_at=(t + span).astimezone(timezone.utc), sensitivity="normal", join_url=m0.join_url, status="scheduled", agenda=agenda or None))
        await db.commit()
        note = ""
        if str(payload.get("invite") or "").strip():
            from app.services.invites import parse_recipients, build_ics
            try: inv = parse_recipients(str(payload["invite"]))
            except ValueError as exc: raise HTTPException(422, str(exc))
            acct = await cal.get_mail(db, user.id)
            if not acct: note = " Invitations were not sent: connect your mail account on the Connections page first."
            else:
                try:
                    await mailer.send(acct, inv, f"Invitation: {title}", f"{user.display_name or user.email} invited you to: {title}\nJoin: {m0.join_url}\n" + (f"Passcode: {room.passcode}\n" if room.passcode else "") + ("Sign in with your account to join.\n" if room.access == "signed_in" else "") + (agenda or ""), build_ics(m0.id, title, start, start + timedelta(minutes=minutes), acct["address"], inv, m0.join_url, (f"Passcode: {room.passcode}\n" if room.passcode else "") + agenda))
                    note = f" Invitations sent to {len(inv)}."
                except mailer.MailError as exc: note = f" The room was created but invitations could not be sent: {exc}"
        return {"id": m0.id, "join_url": m0.join_url, "access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room, "message": ("Recurring meeting created: %d occurrences with one link. " % len(times) if recurring else "Meeting room created. Share the link; it opens in any browser. ") + note}
    elif payload.get("join_url"):
        from app.services.meeting_links import provider_for
        u = str(payload["join_url"]).strip()
        if not provider_for(u): raise HTTPException(422, "That link is not a Zoom, Teams, Google Meet or Webex address.")
        join = u
    m = Meeting(owner_id=user.id, external_id=ext, title=title, organizer=user.email, start_at=start.astimezone(timezone.utc), end_at=(start + timedelta(minutes=minutes)).astimezone(timezone.utc),
                sensitivity="normal", join_url=join, status="scheduled", agenda=agenda or None)
    times = _series(start, payload.get("recurrence")) if ext.startswith("local:") else [start]
    start = times[0]; m.start_at = start.astimezone(timezone.utc); m.end_at = (start + timedelta(minutes=minutes)).astimezone(timezone.utc)
    if len(times) > 1:
        m.external_id = f"{ext}#1"
        for k, t in enumerate(times[1:], 2):
            db.add(Meeting(owner_id=user.id, external_id=f"{ext}#{k}", title=title, organizer=user.email, start_at=t.astimezone(timezone.utc), end_at=(t + timedelta(minutes=minutes)).astimezone(timezone.utc), sensitivity="normal", join_url=join, status="scheduled", agenda=agenda or None))
    invited, invite_note = [], ""
    if str(payload.get("invite") or "").strip():
        from app.services.invites import parse_recipients, build_ics
        try: invited = parse_recipients(str(payload["invite"]))
        except ValueError as exc: raise HTTPException(422, str(exc))
    db.add(m); db.add(AuditLog(actor=user.email, action="meeting.create", resource_type="meeting", safe_metadata={"zoom": bool(join and ext.startswith("zoom:"))})); await db.commit()
    await db.refresh(m)
    if invited:
        acct = await cal.get_mail(db, user.id)
        if not acct: invite_note = " Invitations were not sent: connect your mail account on the Connections page first."
        else:
            try:
                ics = build_ics(m.id, title, start, start + timedelta(minutes=minutes), acct["address"], invited, join, agenda)
                body = f"{user.display_name or user.email} invited you to: {title}\nWhen: {start.astimezone(tz).strftime('%A %d %B %Y, %H:%M')} ({tz})\n" + (f"Join: {join}\n" if join else "") + (f"\n{agenda}\n" if agenda else "")
                await mailer.send(acct, invited, f"Invitation: {title}", body, ics)
                invite_note = f" Invitations sent to {len(invited)} {'person' if len(invited) == 1 else 'people'}."
            except mailer.MailError as exc: invite_note = f" The meeting was created but invitations could not be sent: {exc}"
    base_msg = {"zoom": "Zoom meeting created.", "teams": "Microsoft Teams meeting created.", "meet": "Google Meet meeting created."}.get(ext.split(":")[0], "Meeting added.")
    return {"id": m.id, "join_url": join, "message": (f"Recurring meeting created: {len(times)} occurrences. " if len(times) > 1 else base_msg) + invite_note}


@router.post("/connections/mail")
async def save_mail_account(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    prov = payload.get("provider") if payload.get("provider") in mailer.PRESETS else "other"; pre = mailer.PRESETS[prov]
    address = str(payload.get("address") or "").strip().lower(); password = str(payload.get("password") or "")
    from app.services.invites import EMAIL
    if not EMAIL.match(address) or not password: raise HTTPException(422, "Enter your email address and an app password.")
    acct = {"provider": prov, "address": address, "username": str(payload.get("username") or address).strip(), "password": password,
            "smtp_host": str(payload.get("smtp_host") or pre["smtp"][0]).strip(), "smtp_port": int(payload.get("smtp_port") or pre["smtp"][1]),
            "imap_host": str(payload.get("imap_host") or pre["imap"][0]).strip(), "imap_port": int(payload.get("imap_port") or pre["imap"][1]),
            "import_invites": bool(payload.get("import_invites"))}
    try: await mailer.test(acct)
    except mailer.MailError as exc: raise HTTPException(422, str(exc))
    stored = dict(acct); stored["password"] = rs._enc(password); stored.update(ok=True, error=None, at=datetime.now(timezone.utc).isoformat())
    await cal.save_mail(db, user.id, stored)
    db.add(AuditLog(actor=user.email, action="mail.account.save", resource_type="mail", safe_metadata={"provider": prov})); await db.commit()
    msg = "Mail account connected. Invitations will be sent from it."
    if acct["import_invites"]:
        try: r = await cal.sync_calendar(db, user.id); msg += f" Calendar invitations found in your inbox were added ({r['added']} new)."
        except GraphUnavailable: pass
    return {"message": msg, "mail": await _mail_public(db, user)}

@router.delete("/connections/mail")
async def remove_mail_account(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await cal.save_mail(db, user.id, None)
    db.add(AuditLog(actor=user.email, action="mail.account.remove", resource_type="mail", safe_metadata={})); await db.commit()
    return {"mail": None}

@router.post("/connections/mail/test")
async def send_test_mail(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    acct = await cal.get_mail(db, user.id)
    if not acct: raise HTTPException(404, "Connect a mail account first.")
    try: await mailer.send(acct, [acct["address"]], "iSift test message", "Your mail account is connected. Meeting invitations will be sent from this address.")
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    return {"message": f"Test message sent to {acct['address']}."}


async def _cancel_effects(db: AsyncSession, user: User, m: Meeting) -> str:
    """Close the room / remove the event at the supplier. Returns a short note for the person."""
    ext = m.external_id or ""
    if not ext.startswith(("room:", "local:", "zoom:", "teams:", "meet:")):
        raise HTTPException(409, "This meeting comes from your calendar. Change or delete it in your calendar app.")
    note = ""
    if ext.startswith("room:") and "#" not in ext:
        from app.api.routes_rooms import end_room
        from app.models import Room
        room = (await db.execute(select(Room).where(Room.code == ext[5:].split('#')[0]))).scalar_one_or_none()
        if room: await end_room(db, room, True)
    if ext.startswith("zoom:"): note = " It is still scheduled in Zoom; delete it there too if needed."
    if ext.startswith("teams:"):
        try: await GraphClient().delete_event(mailbox_for(user.email) or "", ext[6:]); note = " It was also removed from Microsoft 365."
        except Exception: note = " It may still be on your Microsoft 365 calendar; delete it there too."
    if ext.startswith("meet:"):
        try: await google.delete_event(google.subject_for(user.email) or "", ext[5:]); note = " It was also removed from Google Calendar."
        except Exception: note = " It may still be on your Google calendar; delete it there too."
    return note

@router.post("/meetings/{meeting_id}/cancel")
async def cancel_meeting(meeting_id: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Cancel a meeting created here. A built-in room is also closed for everyone. (A Zoom meeting is only marked
    cancelled in this app; delete it in Zoom as well if it should disappear there.)"""
    m = await db.get(Meeting, meeting_id)
    if not m or m.owner_id != user.id: raise HTTPException(404, "Meeting not found")
    note = await _cancel_effects(db, user, m)
    m.status = "cancelled"
    db.add(AuditLog(actor=user.email, action="meeting.cancel", resource_type="meeting", safe_metadata={})); await db.commit()
    return {"ok": True, "message": "Meeting cancelled." + note}

@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, series: bool = False, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Delete a meeting created here (and, with series=true, every meeting of the same recurring series). The room is closed
    and any Zoom/Teams/Meet event is removed where possible. A meeting that already has a transcript, minutes or action items
    is cancelled instead so those records are kept."""
    from app.models import Room, Transcript, Minutes, ActionItem
    m = await db.get(Meeting, meeting_id)
    admin_for_other = bool(m and m.owner_id != user.id and user.role == "admin")      # an administrator may delete anyone's iSift room meeting
    if not m or (m.owner_id != user.id and not admin_for_other): raise HTTPException(404, "Meeting not found")
    if admin_for_other and not (m.external_id or "").startswith(("room:", "local:")): raise HTTPException(403, "Only the person who scheduled a Zoom, Teams or Google Meet meeting can delete it, because it also lives in their account there.")
    targets = [m]
    ext = m.external_id or ""
    if series and ext.startswith(("room:", "local:")) and "#" in ext:
        stem = ext.split("#")[0] + "#"
        targets = list((await db.execute(select(Meeting).where(Meeting.owner_id == m.owner_id, Meeting.external_id.like(stem + "%")))).scalars().all())
    removed = kept = 0; note = ""
    from sqlalchemy import update as sqlupdate, delete as sqldelete
    from app.models import Booking
    ids = [t.id for t in targets]; has: set[str] = set()
    for i in range(0, len(ids), 400):                                       # one query per kind of record for a whole batch, not one per meeting (a 365-day series must not take 2,000 round trips)
        chunk = ids[i:i + 400]
        for model in (Transcript, Minutes, ActionItem): has |= set((await db.execute(select(model.meeting_id).where(model.meeting_id.in_(chunk)))).scalars().all())
    gone = []
    for t in targets:
        imported = not (t.external_id or "").startswith(("room:", "local:", "zoom:", "teams:", "meet:"))
        if imported: note = " It was removed from iSift only; it stays in your calendar app and may return when you sync again."
        elif t.status != "cancelled": note = await _cancel_effects(db, user, t) or note
        if t.id in has: t.status = "cancelled"; kept += 1
        else: gone.append(t)
    for i in range(0, len(gone), 400):
        chunk = [t.id for t in gone[i:i + 400]]
        await db.execute(sqlupdate(Room).where(Room.meeting_id.in_(chunk)).values(meeting_id=None))
        await db.execute(sqlupdate(Booking).where(Booking.meeting_id.in_(chunk)).values(meeting_id=None))
        for t in gone[i:i + 400]: db.expunge(t)
        await db.execute(sqldelete(Meeting).where(Meeting.id.in_(chunk)))
    removed = len(gone)
    await db.flush()
    from app.api.routes_rooms import end_room
    from app.models import Room as _Room
    for code in {(t.external_id or "")[5:].split("#")[0] for t in targets if (t.external_id or "").startswith("room:")}:
        left = (await db.execute(select(Meeting.id).where(Meeting.external_id.like(f"room:{code}%"), Meeting.status != "cancelled").limit(1))).first()
        rm = (await db.execute(select(_Room).where(_Room.code == code))).scalar_one_or_none()
        if rm and not left and not (rm.options or {}).get("pmi"): await end_room(db, rm, True)           # the last meeting of a series is gone: the shared link stops working too (a personal room is never closed)
    db.add(AuditLog(actor=user.email, action="meeting.delete", resource_type="meeting", safe_metadata={"count": len(targets), **({"owner": m.organizer} if admin_for_other else {})})); await db.commit()
    msg = (f"{removed} meeting{'s' if removed != 1 else ''} deleted." if removed else "Meeting cancelled.") + (f" {kept} kept as cancelled because transcripts or minutes exist." if kept else "") + note
    return {"ok": True, "message": msg, "removed": removed}


def _pick_zone(payload: dict, default):
    """The time zone chosen on the form (an IANA name), else the person's own."""
    from zoneinfo import ZoneInfo
    name = str(payload.get("timezone") or "").strip()
    if name:
        try: return ZoneInfo(name)
        except Exception: pass
    return default

def _series(start: datetime, rec: dict | None) -> list[datetime]:
    """Start times for a recurring meeting: daily, weekly or monthly at the same wall-clock time, either for N meetings or up to
    and including a last day (YYYY-MM-DD), or with no end date (a year of daily/weekly meetings, two years monthly). At most 365 occurrences."""
    import calendar
    out = [start]
    if not isinstance(rec, dict): return out
    every = str(rec.get("every") or "")
    if every not in ("day", "week", "month"): return out
    until = None
    if rec.get("until"):
        try: until = datetime.fromisoformat(str(rec["until"])[:10]).date()
        except ValueError: raise HTTPException(422, "Choose a valid last day for the repeat.")
        if until < start.date(): raise HTTPException(422, "The last day must be on or after the first meeting.")
    days = sorted({int(d) for d in (rec.get("days") or []) if str(d).isdigit() and 0 <= int(d) <= 6})
    forever = bool(rec.get("forever")) and not until
    if every == "week" and days:                      # chosen weekdays (0 = Monday), for N weeks, up to a last day, or with no end date (a year)
        weeks = max(1, min(52, int(rec.get("weeks") or 1)))
        monday = start - timedelta(days=start.weekday()); out = []
        for w in range(52 if (until or forever) else weeks):
            for d in days:
                t = monday + timedelta(days=7 * w + d)
                if t < start or (until and t.date() > until): continue
                out.append(t)
        if not out: raise HTTPException(422, "No meeting falls on the chosen days. Pick other days or a later last day.")
        return out[:400]
    n = 366 if until else {"day": 365, "week": 52, "month": 24}[every] if forever else max(1, min(365, int(rec.get("count") or 1)))
    for k in range(1, n):
        if every == "month":
            mo = start.month - 1 + k; y, m = start.year + mo // 12, mo % 12 + 1
            d = min(start.day, calendar.monthrange(y, m)[1]); t = start.replace(year=y, month=m, day=d)
        else: t = start + timedelta(days=k * (1 if every == "day" else 7))
        if until and t.date() > until: break
        out.append(t)
    return out

# ---------------- open, view and change a meeting (like a Zoom meeting page) ----------------
import re as _re

def _aware(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d

def _kind(m: Meeting) -> str:
    ext = m.external_id or ""
    return "room" if ext.startswith("room:") else "zoom" if ext.startswith("zoom:") else "teams" if ext.startswith("teams:") else "meet" if ext.startswith("meet:") else "local" if ext.startswith("local:") else "calendar"

async def _room_for(db: AsyncSession, m: Meeting):
    from app.models import Room
    if not (m.external_id or "").startswith("room:"): return None
    return (await db.execute(select(Room).where(Room.code == m.external_id[5:].split('#')[0]))).scalar_one_or_none()

def _details(m: Meeting, room) -> dict:
    kind = _kind(m)
    zid = None
    if kind == "zoom": zid = (m.external_id or "")[5:] or None
    opts = dict((room.options or {}) if room else {})
    return {"id": m.id, "title": m.title, "agenda": m.agenda or "", "start_at": _aware(m.start_at).isoformat(),
            "duration_minutes": max(5, int((_aware(m.end_at) - _aware(m.start_at)).total_seconds() // 60)), "status": m.status, "kind": kind, "join_url": m.join_url,
            "meeting_id": room.code if room else zid, "passcode": room.passcode if room else None, "access": room.access if room else None,
            "waiting_room": room.waiting_room if room else None, "ended": bool(room and room.ended_at),
            "options": {k: bool(opts.get(k)) for k in ("mute_on_entry", "video_off_on_entry", "auto_record", "host_video_off")} | {"virtual_room": opts.get("virtual_room", False) is True}, "invitees": opts.get("invitees", []),
            "series": "#" in (m.external_id or ""), "pmi": bool(opts.get("pmi")),
            "editable": kind in ("room", "zoom", "teams", "meet", "local") and m.status != "cancelled", "organizer": __import__("app.services.identity", fromlist=["x"]).shown_email(m.organizer or "")}

@router.get("/meetings/{meeting_id}/details")
async def meeting_details(meeting_id: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    m = await db.get(Meeting, meeting_id)
    if not m or m.owner_id != user.id: raise HTTPException(404, "Meeting not found")
    return _details(m, await _room_for(db, m))

@router.patch("/meetings/{meeting_id}")
async def change_meeting(meeting_id: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Edit a meeting created here: topic, description, time, length and (for built-in meetings) security and options."""
    m = await db.get(Meeting, meeting_id)
    if not m or m.owner_id != user.id: raise HTTPException(404, "Meeting not found")
    kind = _kind(m)
    if kind == "calendar": raise HTTPException(409, "This meeting comes from your calendar. Change it in your calendar app.")
    if m.status == "cancelled": raise HTTPException(409, "This meeting was cancelled.")
    tz = _pick_zone(payload, await cal.user_timezone(db))
    if "title" in payload:
        t = str(payload["title"]).strip()[:200]
        if not t: raise HTTPException(422, "Give the meeting a title.")
        m.title = t
    if "agenda" in payload: m.agenda = str(payload["agenda"] or "")[:2000] or None
    dur = max(5, int((_aware(m.end_at) - _aware(m.start_at)).total_seconds() // 60))
    if "duration_minutes" in payload:
        try: dur = int(payload["duration_minutes"])
        except (TypeError, ValueError): raise HTTPException(422, "Duration must be a number of minutes.")
        if not 5 <= dur <= 720: raise HTTPException(422, "Duration must be between 5 minutes and 12 hours.")
    if "start_at" in payload:
        try: st = datetime.fromisoformat(str(payload["start_at"]).replace("Z", "+00:00"))
        except ValueError: raise HTTPException(422, "Choose a valid start date and time.")
        if st.tzinfo is None: st = st.replace(tzinfo=tz)
        m.start_at = st.astimezone(timezone.utc)
    m.end_at = _aware(m.start_at) + timedelta(minutes=dur)
    room = await _room_for(db, m)
    if "start_at" in payload and _aware(m.end_at) > datetime.now(timezone.utc):          # moved to a time that has not finished: an ended meeting is open again
        if m.status == "completed": m.status = "scheduled"
        if room and room.ended_at is not None and not (room.options or {}).get("pmi"): room.ended_at = None
    if room:
        from app.api.routes_rooms import clean_access, clean_options
        room.title = m.title[:200]
        if "access" in payload or "passcode" in payload:
            new_access = payload.get("access", room.access)
            room.access, room.passcode = clean_access(new_access, payload.get("passcode") or (room.passcode if new_access == "passcode" else None))
            room.allow_guests = room.access != "signed_in"
        if "waiting_room" in payload: room.waiting_room = bool(payload["waiting_room"])
        opts = dict(payload.get("options") or {})
        if payload.get("add_invitees"):
            from app.services.invites import parse_recipients
            try: new = parse_recipients(str(payload["add_invitees"]))
            except ValueError as exc: raise HTTPException(422, str(exc))
            opts["invitees"] = sorted(set(room.options.get("invitees", [])) | set(new))
        room.options = clean_options(opts, keep=room.options or {})
        if room.options.get("open_room"): room.access, room.passcode, room.waiting_room, room.allow_guests = "open", None, False, True; room.ended_at = None
    db.add(AuditLog(actor=user.email, action="meeting.update", resource_type="meeting", safe_metadata={}))
    await db.commit()
    note = ""
    if payload.get("send_update") and room and (room.options or {}).get("invitees"):
        acct = await cal.get_mail(db, user.id)
        if not acct: note = " Updates were not sent: connect your mail account on the Connections page first."
        else:
            from app.services.invites import build_ics
            try:
                inv = room.options["invitees"]
                body = (f"{user.display_name or user.email} updated the meeting: {m.title}\nWhen: {_aware(m.start_at).astimezone(tz).strftime('%A %d %B %Y, %H:%M')} ({tz})\nJoin: {m.join_url}\n"
                        + (f"Meeting ID: {room.code}\n" if room else "") + (f"Passcode: {room.passcode}\n" if room.passcode else "") + ("Sign in with your account to join.\n" if room.access == "signed_in" else "") + (f"\n{m.agenda}\n" if m.agenda else ""))
                await mailer.send(acct, inv, f"Updated: {m.title}", body, build_ics(m.id, m.title, _aware(m.start_at), _aware(m.end_at), acct["address"], inv, m.join_url, (f"Passcode: {room.passcode}\n" if room.passcode else "") + (m.agenda or ""), sequence=int(datetime.now(timezone.utc).timestamp())))
                note = f" Updated invitation sent to {len(inv)}."
            except mailer.MailError as exc: note = f" Saved, but the update could not be emailed: {exc}"
    return {**_details(m, room), "message": "Meeting saved." + note}


@router.get("/admin/meetings")
async def admin_meetings(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Every iSift room meeting that is not cancelled, for an administrator who needs to remove one."""
    from app.models import Room
    rows = (await db.execute(select(Meeting, User.email).join(User, User.id == Meeting.owner_id).where(Meeting.external_id.like("room:%"), Meeting.status != "cancelled").order_by(Meeting.start_at.desc()).limit(300))).all()
    rooms = {r.code: r for r in (await db.execute(select(Room))).scalars().all()}
    out = []
    for m, email in rows:
        code = (m.external_id or "")[5:].split("#")[0]; r = rooms.get(code)
        out.append({"id": m.id, "title": m.title, "owner": email, "start_at": m.start_at.isoformat(), "series": "#" in (m.external_id or ""), "open_room": bool(r and (r.options or {}).get("open_room")), "personal": bool(r and (r.options or {}).get("pmi")), "join_url": m.join_url})
    return {"meetings": out}
