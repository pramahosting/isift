"""YouTube publishing for Podcast Studio.

YouTube never accepts a password. A person connects their channel once: they give iSift the Google sign-in details of an app they
own (a Client ID and Client secret from their Google Cloud project; an administrator may also set one for everybody) and then sign
in to Google and approve. iSift keeps only an encrypted refresh token, and uses it to upload with the YouTube Data API
(resumable upload, so a big file survives a bad connection).

Note: Google keeps videos uploaded through an app that has not passed its audit private. Posting works at once, and public posting
needs the app to be verified by Google (a one-off review that is the app owner's to request)."""
import hashlib, time
from pathlib import Path
from urllib.parse import urlencode
import httpx
from app.core.config import settings

class YouTubeError(RuntimeError): pass

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
CHANNELS = "https://www.googleapis.com/youtube/v3/channels"
SCOPE = "openid email https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
PRIVACY = ("private", "unlisted", "public")
CHUNK = 16 * 256 * 1024 * 2            # 8 MiB: a multiple of 256 KiB, as the resumable protocol needs
MAX_TITLE, MAX_DESC = 100, 5000

def http(timeout: float = 60) -> httpx.AsyncClient:
    """One place to get a client, so tests can swap the network out."""
    return httpx.AsyncClient(timeout=timeout)

def platform_client() -> tuple[str, str]:
    """The Google app set up once by an administrator for everybody: a YouTube-only one if given, otherwise the Google sign-in app used for mail."""
    if settings.youtube_oauth_client_id and settings.youtube_oauth_client_secret: return settings.youtube_oauth_client_id, settings.youtube_oauth_client_secret
    return settings.google_oauth_client_id or "", settings.google_oauth_client_secret or ""

def platform_source() -> str:
    if settings.youtube_oauth_client_id and settings.youtube_oauth_client_secret: return "youtube"
    return "google" if settings.google_oauth_client_id and settings.google_oauth_client_secret else "none"

async def check_client(client_id: str, client_secret: str, redirect: str = "https://example.invalid/cb") -> tuple[bool, str]:
    """Is this Client ID and secret accepted by Google? A made-up sign-in code is sent: a good client answers "invalid_grant", a wrong one "invalid_client"."""
    try:
        async with http(20) as c:
            r = await c.post(TOKEN, data={"grant_type": "authorization_code", "code": "isift-check", "redirect_uri": redirect, "client_id": client_id, "client_secret": client_secret})
    except httpx.HTTPError as exc: return False, f"Could not reach Google ({type(exc).__name__})."
    try: j = r.json() or {}
    except Exception: j = {}
    e = j.get("error", ""); why = str(j.get("error_description") or "")[:160]
    # Google checks the client first, so any answer about the made-up code (or the request itself) means the ID and secret were accepted
    if e in ("invalid_grant", "redirect_uri_mismatch", "invalid_request"): return True, "Google accepts this Client ID and secret."
    if e == "invalid_client": return False, "Google does not recognise this Client ID and secret. Check them in Google Cloud > APIs & Services > Credentials."
    return False, f"Google answered unexpectedly ({r.status_code} {e or 'no reason given'}{': ' + why if why else ''})."

def pkce_pair() -> tuple[str, str]:
    import base64, secrets
    v = secrets.token_urlsafe(48)
    return v, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()

def auth_url(client_id: str, redirect: str, state: str, challenge: str, hint: str = "") -> str:
    q = {"client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "state": state, "code_challenge": challenge,
         "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent select_account", "include_granted_scopes": "true"}
    if hint: q["login_hint"] = hint
    return AUTH + "?" + urlencode(q)

async def _token(data: dict, client_id: str, client_secret: str) -> dict:
    try:
        async with http(25) as c: r = await c.post(TOKEN, data={**data, "client_id": client_id, "client_secret": client_secret})
    except httpx.HTTPError as exc: raise YouTubeError(f"Could not reach Google ({type(exc).__name__}).")
    try: j = r.json()
    except Exception: j = {}
    if r.status_code >= 400 or "access_token" not in j:
        why = j.get("error_description") or j.get("error") or str(r.status_code)
        if j.get("error") == "invalid_client": why = "Google does not recognise this Client ID and secret. Check them in your Google Cloud project."
        if j.get("error") == "invalid_grant": why = "The YouTube connection has expired or was removed. Connect YouTube again."
        raise YouTubeError("Google refused the sign-in: " + why)
    return j

async def exchange_code(client_id: str, client_secret: str, code: str, redirect: str, verifier: str) -> dict:
    return await _token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect, "code_verifier": verifier}, client_id, client_secret)

_CACHE: dict[str, tuple[str, float]] = {}
async def access_token(client_id: str, client_secret: str, refresh: str) -> str:
    key = hashlib.sha256((client_id + refresh).encode()).hexdigest()
    hit = _CACHE.get(key)
    if hit and hit[1] > time.time() + 60: return hit[0]
    j = await _token({"grant_type": "refresh_token", "refresh_token": refresh}, client_id, client_secret)
    _CACHE[key] = (j["access_token"], time.time() + int(j.get("expires_in", 3000)))
    return j["access_token"]

async def whoami(token: str) -> dict:
    """The signed-in Google address and the YouTube channel name, for showing which channel is connected."""
    out = {"email": "", "channel": "", "channel_id": ""}
    try:
        async with http(20) as c:
            u = await c.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {token}"})
            if u.status_code < 400: out["email"] = (u.json().get("email") or "").lower()
            ch = await c.get(CHANNELS, params={"part": "snippet", "mine": "true"}, headers={"Authorization": f"Bearer {token}"})
            if ch.status_code < 400:
                items = ch.json().get("items") or []
                if items: out["channel"] = (items[0].get("snippet") or {}).get("title", ""); out["channel_id"] = items[0].get("id", "")
    except httpx.HTTPError: pass
    return out

def clean_meta(title: str, description: str, privacy: str, tags: list[str] | None, made_for_kids: bool = False) -> dict:
    title = " ".join((title or "").replace("<", "").replace(">", "").split())[:MAX_TITLE] or "Podcast"
    tags = [t.strip()[:30] for t in (tags or []) if t and t.strip()][:15]
    return {"snippet": {"title": title, "description": (description or "").replace("<", "").replace(">", "")[:MAX_DESC], "tags": tags, "categoryId": "22"},
            "status": {"privacyStatus": privacy if privacy in PRIVACY else "private", "selfDeclaredMadeForKids": bool(made_for_kids)}}

async def upload(token: str, path: Path, meta: dict, mime: str, on_progress=None) -> dict:
    """Resumable upload. Returns {"id", "url"}. await on_progress(percent) is called as the file goes."""
    size = path.stat().st_size
    if size <= 0: raise YouTubeError("The video file is empty.")
    head = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": mime or "video/*", "X-Upload-Content-Length": str(size)}
    async with http(120) as c:
        try: r = await c.post(UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"}, headers=head, json=meta)
        except httpx.HTTPError as exc: raise YouTubeError(f"Could not reach YouTube ({type(exc).__name__}).")
        if r.status_code >= 400: raise YouTubeError(_why(r))
        loc = r.headers.get("location")
        if not loc: raise YouTubeError("YouTube did not give an upload address. Try again.")
        sent, tries = 0, 0
        with path.open("rb") as f:
            while sent < size:
                f.seek(sent); chunk = f.read(CHUNK); end = sent + len(chunk) - 1
                try:
                    r = await c.put(loc, content=chunk, headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {sent}-{end}/{size}", "Content-Type": mime or "video/*"})
                except httpx.HTTPError as exc:
                    tries += 1
                    if tries > 5: raise YouTubeError(f"The upload to YouTube kept failing ({type(exc).__name__}).")
                    sent = await _resume(c, loc, size, sent); continue
                if r.status_code in (200, 201):
                    j = r.json(); vid = j.get("id", "")
                    if on_progress: await on_progress(100)
                    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
                if r.status_code == 308:
                    rng = r.headers.get("range", ""); sent = int(rng.split("-")[-1]) + 1 if rng else sent + len(chunk)
                    if on_progress: await on_progress(min(99, int(sent * 100 / size)))
                    continue
                if r.status_code in (500, 502, 503, 504):
                    tries += 1
                    if tries > 5: raise YouTubeError("YouTube is not accepting the upload right now. Try again later.")
                    sent = await _resume(c, loc, size, sent); continue
                raise YouTubeError(_why(r))
    raise YouTubeError("The upload to YouTube did not finish.")

async def _resume(c: httpx.AsyncClient, loc: str, size: int, sent: int) -> int:
    """Ask YouTube how much of the file it already has."""
    try:
        r = await c.put(loc, headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"})
        if r.status_code == 308:
            rng = r.headers.get("range", ""); return int(rng.split("-")[-1]) + 1 if rng else 0
    except httpx.HTTPError: pass
    return sent

def _why(r: httpx.Response) -> str:
    try: e = (r.json().get("error") or {}); reason = ((e.get("errors") or [{}])[0].get("reason")) or ""; msg = e.get("message") or ""
    except Exception: reason, msg = "", ""
    if reason in ("quotaExceeded", "dailyLimitExceeded"): return "Your YouTube upload limit for today has been used. Try again tomorrow."
    if reason == "youtubeSignupRequired": return "This Google account has no YouTube channel yet. Create one at youtube.com, then connect again."
    if reason in ("forbidden", "insufficientPermissions") or r.status_code == 403: return "YouTube did not allow the upload (" + (msg or reason or "forbidden") + "). Connect YouTube again and accept every permission."
    if r.status_code == 401: return "The YouTube connection has expired. Connect YouTube again."
    return f"YouTube refused the video ({r.status_code}): {msg[:160] or reason or 'unknown reason'}"
