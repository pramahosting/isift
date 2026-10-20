"""Google Meet through the Google Calendar API, using a service account with domain-wide delegation.

Settings come from Admin Console > Meeting platforms > Google Meet. The service account books the event as the person
(or as the configured calendar user for the demo administrator) and Google returns the Meet link.
"""
import json, time, uuid
from datetime import datetime, timezone
import httpx, jwt
from app.core.config import settings

SCOPE = "https://www.googleapis.com/auth/calendar"
API = "https://www.googleapis.com/calendar/v3"

class GoogleUnavailable(RuntimeError): pass

def _key() -> dict | None:
    try:
        j = json.loads(settings.google_service_account_json or "")
        return j if j.get("client_email") and j.get("private_key") else None
    except (ValueError, TypeError): return None

def configured() -> bool:
    return bool(_key())

def subject_for(email: str) -> str | None:
    if email.lower() == "admin@isift.au": return settings.google_calendar_user or None
    return email or None

async def _token(subject: str) -> str:
    k = _key()
    if not k: raise GoogleUnavailable("Google Meet is not configured. An administrator can add it in Admin Console > Meeting platforms.")
    now = int(time.time()); aud = k.get("token_uri") or "https://oauth2.googleapis.com/token"
    try: assertion = jwt.encode({"iss": k["client_email"], "sub": subject, "scope": SCOPE, "aud": aud, "iat": now, "exp": now + 3000}, k["private_key"], algorithm="RS256")
    except Exception: raise GoogleUnavailable("The Google service account key could not be used. Paste the full JSON key again.")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(aud, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    if r.status_code >= 400: raise GoogleUnavailable(f"Google sign-in failed ({r.status_code}). Check domain-wide delegation for {subject} and the Calendar scope.")
    return r.json()["access_token"]

async def create_meet(subject: str, title: str, start: datetime, end: datetime, tz_name: str, agenda: str = "") -> dict:
    token = await _token(subject)
    iso = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"summary": title[:250], "description": agenda[:2000], "start": {"dateTime": iso(start), "timeZone": tz_name}, "end": {"dateTime": iso(end), "timeZone": tz_name},
            "conferenceData": {"createRequest": {"requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"}}}}
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(f"{API}/calendars/primary/events", params={"conferenceDataVersion": 1}, json=body, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400: raise GoogleUnavailable(f"Google could not create the meeting ({r.status_code}). Check that the Calendar API is enabled.")
    j = r.json(); link = j.get("hangoutLink") or next((e.get("uri") for e in (j.get("conferenceData") or {}).get("entryPoints", []) if e.get("entryPointType") == "video"), None)
    if not link: raise GoogleUnavailable("Google created the event but no Meet link came back. Try again in a moment.")
    return {"id": j["id"], "join_url": link}

async def delete_event(subject: str, event_id: str) -> None:
    token = await _token(subject)
    async with httpx.AsyncClient(timeout=25) as c:
        await c.delete(f"{API}/calendars/primary/events/{event_id}", headers={"Authorization": f"Bearer {token}"})
