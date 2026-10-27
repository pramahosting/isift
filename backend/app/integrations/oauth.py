"""'Sign in with Google / Microsoft / Yahoo' for the Mail page, the same way Outlook adds an account: a sign-in popup, the person
approves access, and iSift keeps a refresh token (encrypted) instead of a password. Used with IMAP/SMTP (XOAUTH2) for mail, and the
Google / Microsoft calendar and contacts services."""
import re
import base64, hashlib, secrets, time
from urllib.parse import urlencode
import httpx
from app.core.config import settings

class OAuthError(RuntimeError): pass

MS_MAIL = "https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send"
MS_GRAPH = "https://graph.microsoft.com/Calendars.Read https://graph.microsoft.com/Contacts.Read https://graph.microsoft.com/User.Read"
PROVIDERS = {
    "google": {"label": "Google", "auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token",
               "scope": "openid email profile https://mail.google.com/ https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/contacts.readonly https://www.googleapis.com/auth/contacts.other.readonly",
               "extra": {"access_type": "offline", "prompt": "consent select_account"}, "mail_provider": "gmail", "people": True,
               "imap": ("imap.gmail.com", 993), "smtp": ("smtp.gmail.com", 587), "userinfo": "https://openidconnect.googleapis.com/v1/userinfo"},
    "microsoft": {"label": "Microsoft", "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                  "scope": "openid email profile offline_access " + MS_MAIL + " " + MS_GRAPH, "extra": {"prompt": "select_account"}, "mail_provider": "outlook", "people": True,
                  "imap": ("outlook.office365.com", 993), "smtp": ("smtp.office365.com", 587), "userinfo": "https://graph.microsoft.com/v1.0/me"},
    "yahoo": {"label": "Yahoo", "auth": "https://api.login.yahoo.com/oauth2/request_auth", "token": "https://api.login.yahoo.com/oauth2/get_token",
              "scope": "openid email mail-w", "extra": {"prompt": "login"}, "mail_provider": "yahoo", "people": False,
              "imap": ("imap.mail.yahoo.com", 993), "smtp": ("smtp.mail.yahoo.com", 587), "userinfo": "https://api.login.yahoo.com/openid/v1/userinfo"},
}

def _url(provider: str, key: str) -> str:
    """Sign-in and token addresses. A Microsoft app registered for one company only needs its own tenant ID (MS_OAUTH_TENANT) instead of 'common'."""
    u = PROVIDERS[provider][key]
    if provider == "microsoft":
        t = (settings.ms_oauth_tenant or "common").strip() or "common"
        if t != "common" and re.fullmatch(r"[A-Za-z0-9.\-]{3,100}", t): u = u.replace("/common/", f"/{t}/")
    return u

def creds(provider: str) -> tuple[str, str]:
    return {"google": (settings.google_oauth_client_id, settings.google_oauth_client_secret),
            "microsoft": (settings.ms_oauth_client_id, settings.ms_oauth_client_secret),
            "yahoo": (settings.yahoo_oauth_client_id, settings.yahoo_oauth_client_secret)}[provider]

def ready(provider: str) -> bool:
    cid, sec = creds(provider); return bool(cid and sec)

def pkce() -> tuple[str, str]:
    v = secrets.token_urlsafe(48); return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()

DOMAINS = {"google": ("gmail.com", "googlemail.com"), "microsoft": ("outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.com.au", "hotmail.com.au", "live.com.au", "hotmail.co.uk", "outlook.co.uk", "live.co.uk"),
           "yahoo": ("yahoo.com", "yahoo.com.au", "yahoo.co.uk", "yahoo.co.in", "yahoo.in", "ymail.com", "rocketmail.com", "yahoo.ca", "yahoo.de", "yahoo.fr")}

def detect(email: str) -> str | None:
    d = (email.split("@")[-1] if "@" in email else "").strip().lower()
    return next((k for k, v in DOMAINS.items() if d in v), None)

def auth_url(provider: str, redirect_uri: str, state: str, challenge: str, login_hint: str = "") -> str:
    p = PROVIDERS[provider]; cid, _ = creds(provider)
    q = {"client_id": cid, "redirect_uri": redirect_uri, "response_type": "code", "scope": p["scope"], "state": state, "code_challenge": challenge, "code_challenge_method": "S256", **p["extra"], **({"login_hint": login_hint} if login_hint else {})}
    return _url(provider, "auth") + "?" + urlencode(q)

async def _post(provider: str, data: dict) -> dict:
    cid, sec = creds(provider)
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            if provider == "yahoo":
                r = await c.post(_url(provider, "token"), data=data, auth=(cid, sec))
            else:
                r = await c.post(_url(provider, "token"), data={**data, "client_id": cid, "client_secret": sec})
    except httpx.HTTPError as exc: raise OAuthError(f"Could not reach {PROVIDERS[provider]['label']} ({type(exc).__name__}).")
    j = {}
    try: j = r.json()
    except Exception: pass
    if r.status_code >= 400 or "access_token" not in j:
        raise OAuthError(f"{PROVIDERS[provider]['label']} refused the sign-in: {j.get('error_description') or j.get('error') or r.status_code}")
    return j

async def exchange_code(provider: str, code: str, redirect_uri: str, verifier: str) -> dict:
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier}
    # Microsoft (personal accounts especially) insists on a scope here, from ONE resource. Use Microsoft Graph so the access token can read the
    # person's profile; the refresh token still covers the mail and calendar permissions that were approved, and is swapped for those later.
    if provider == "microsoft": data["scope"] = "openid email profile offline_access " + MS_GRAPH
    return await _post(provider, data)

_CACHE: dict[str, tuple[str, float]] = {}

async def access_token(provider: str, refresh_token: str, kind: str = "mail") -> str:
    """A fresh access token. kind: 'mail' (IMAP/SMTP) or 'graph' (Microsoft calendar and contacts)."""
    key = f"{provider}:{kind}:{hashlib.sha256(refresh_token.encode()).hexdigest()[:16]}"
    hit = _CACHE.get(key)
    if hit and hit[1] > time.time() + 60: return hit[0]
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    if provider == "microsoft": data["scope"] = (MS_MAIL if kind == "mail" else MS_GRAPH) + " offline_access"
    j = await _post(provider, data)
    _CACHE[key] = (j["access_token"], time.time() + int(j.get("expires_in", 3000)))
    return j["access_token"]

async def whoami(provider: str, token: str) -> dict:
    p = PROVIDERS[provider]
    async with httpx.AsyncClient(timeout=20) as c: r = await c.get(p["userinfo"], headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400: raise OAuthError("Could not read your account details after sign-in.")
    j = r.json()
    email = (j.get("email") or j.get("mail") or j.get("userPrincipalName") or "").lower()
    return {"email": email, "name": j.get("name") or j.get("displayName") or ""}

def xoauth2(user: str, token: str) -> str:
    return f"user={user}\x01auth=Bearer {token}\x01\x01"

# ---------------- Google calendar and contacts ----------------
async def google_calendar(token: str, start, end) -> list[dict]:
    from datetime import timezone
    f = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get("https://www.googleapis.com/calendar/v3/calendars/primary/events", headers={"Authorization": f"Bearer {token}"},
                        params={"timeMin": f(start), "timeMax": f(end), "singleEvents": "true", "orderBy": "startTime", "maxResults": "250"})
    if r.status_code >= 400: raise OAuthError("Google did not allow reading the calendar. Sign in again and accept the calendar permission.")
    from datetime import datetime
    from app.services.meeting_links import find_join_url
    for e in r.json().get("items", []):
        s, en = e.get("start", {}), e.get("end", {})
        allday = "date" in s
        try:
            sd = datetime.fromisoformat(s["dateTime"].replace("Z", "+00:00")) if not allday else datetime.fromisoformat(s["date"] + "T00:00:00+00:00")
            ed = datetime.fromisoformat(en["dateTime"].replace("Z", "+00:00")) if not allday else datetime.fromisoformat(en["date"] + "T00:00:00+00:00")
        except Exception: continue
        fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000")
        me = next((a for a in e.get("attendees", []) if a.get("self")), {})
        out.append({"id": "google:" + e["id"], "subject": e.get("summary") or "Meeting", "sensitivity": {"private": "private", "confidential": "confidential"}.get(e.get("visibility"), "normal"),
                    "onlineMeetingUrl": e.get("hangoutLink") or find_join_url(e.get("location"), e.get("description")), "isCancelled": e.get("status") == "cancelled", "isAllDay": allday,
                    "responseStatus": {"response": {"declined": "declined", "tentative": "tentativelyAccepted"}.get(me.get("responseStatus"), "accepted")},
                    "start": {"dateTime": fmt(sd)}, "end": {"dateTime": fmt(ed)}, "organizer": {"emailAddress": {"address": (e.get("organizer") or {}).get("email", "")}}})
    return out

async def google_contacts(token: str) -> list[dict]:
    out = []; page = ""
    async with httpx.AsyncClient(timeout=25) as c:
        for _ in range(5):
            r = await c.get("https://people.googleapis.com/v1/people/me/connections", headers={"Authorization": f"Bearer {token}"},
                            params={"personFields": "names,emailAddresses,phoneNumbers", "pageSize": "500", **({"pageToken": page} if page else {})})
            if r.status_code >= 400:
                try: why = (r.json().get("error") or {}).get("message", "")
                except Exception: why = ""
                raise OAuthError("Google did not allow reading contacts" + (f" ({why[:140]})" if why else "") + ". Remove iSift from your Google account's connected apps, sign in again and accept the contacts permission.")
            j = r.json()
            for p in j.get("connections", []):
                em = (p.get("emailAddresses") or [{}])[0].get("value", ""); nm = (p.get("names") or [{}])[0].get("displayName", "") or em
                ph = (p.get("phoneNumbers") or [{}])[0].get("value", "")
                if nm: out.append({"name": nm, "email": em, "phone": ph})
            page = j.get("nextPageToken", "")
            if not page: break
        page = ""                      # "Other contacts": people you have emailed but never saved. Optional, so a refusal is ignored.
        for _ in range(5):
            r = await c.get("https://people.googleapis.com/v1/otherContacts", headers={"Authorization": f"Bearer {token}"},
                            params={"readMask": "names,emailAddresses,phoneNumbers", "pageSize": "500", **({"pageToken": page} if page else {})})
            if r.status_code >= 400: break
            j = r.json()
            for p in j.get("otherContacts", []):
                em = (p.get("emailAddresses") or [{}])[0].get("value", ""); nm = (p.get("names") or [{}])[0].get("displayName", "") or em
                if em: out.append({"name": nm, "email": em, "phone": ""})
            page = j.get("nextPageToken", "")
            if not page: break
    return out
