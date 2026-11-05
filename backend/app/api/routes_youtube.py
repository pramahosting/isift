"""Post a podcast to YouTube with one click.

Settings (Podcast settings > YouTube): the person enters the Client ID and Client secret of their own Google Cloud app (or uses the one an
administrator set up for everybody), signs in to Google once, and iSift keeps an encrypted refresh token. YouTube never receives or
stores a password. Posting is then one button on any cloud podcast or edited video.

  GET    /podcasts/youtube               connection status
  PUT    /podcasts/youtube/credentials   save the Client ID and secret
  POST   /podcasts/youtube/connect       start the Google sign-in (returns the address for the popup)
  GET    /podcasts/youtube/callback      where Google sends the person back
  DELETE /podcasts/youtube               disconnect
  POST   /podcasts/{group_id}/youtube    upload the video; progress is read from GET /podcasts/jobs/{id}
"""
import asyncio, html, json, logging, shutil, subprocess, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal, require_admin
from app.core import runtime_settings as rs
from app.models import User, PodcastRecording, IntegrationSetting, AuditLog
from app.api.routes_podcast import _gate
from app.services import youtube as yt, podwork

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/podcasts", tags=["podcast-youtube"])
KEY = lambda uid: f"youtube:{uid}"

async def _conn(db: AsyncSession, uid: str) -> dict:
    row = await db.get(IntegrationSetting, KEY(uid)); return dict(row.value) if row else {}

async def _put(db: AsyncSession, uid: str, value: dict) -> None:
    row = await db.get(IntegrationSetting, KEY(uid))
    if row: row.value = value
    else: db.add(IntegrationSetting(key=KEY(uid), value=value))
    await db.commit()

def _client(c: dict) -> tuple[str, str, bool]:
    """(client id, client secret, is the platform's own). The person's own app wins over the one an administrator set up."""
    if c.get("client_id") and c.get("client_secret"): return c["client_id"], rs._dec(c["client_secret"]), False
    cid, sec = yt.platform_client()
    return cid, sec, True

def _origin(raw) -> str:
    o = urlsplit(str(raw or ""))
    if o.scheme not in ("http", "https") or not o.netloc: raise HTTPException(422, "Missing page address.")
    return f"{o.scheme}://{o.netloc}"

@router.get("/youtube")
async def status(origin: str = "", user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _gate(db, user); await rs.apply_overrides(db)
    c = await _conn(db, user.id); cid, sec, shared = _client(c)
    redirect = (_origin(origin) if origin else settings.frontend_origin.rstrip("/")) + "/api/v1/podcasts/youtube/callback"
    return {"connected": bool(c.get("refresh_token")), "channel": c.get("channel", ""), "email": c.get("email", ""), "connected_at": c.get("connected_at", ""),
            "client_id": c.get("client_id", ""), "has_secret": bool(c.get("client_secret")), "can_connect": bool(cid and sec), "using_shared_app": bool(cid and sec and shared), "shared_ready": bool(yt.platform_client()[0] and yt.platform_client()[1]),
            "redirect_uri": redirect, "default_privacy": c.get("default_privacy", "private")}

@router.get("/admin/youtube-setup")
async def admin_setup(origin: str = "", admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """What the administrator still has to do in Google Cloud so everybody can post to YouTube with one click."""
    await rs.apply_overrides(db)
    cid, sec = yt.platform_client(); src = yt.platform_source()
    base = (_origin(origin) if origin else settings.frontend_origin.rstrip("/"))
    return {"source": src, "client_id": cid, "ready": bool(cid and sec), "redirect_uri": base + "/api/v1/podcasts/youtube/callback",
            "mail_redirect_uri": base + "/api/v1/oauth/callback", "scopes": ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"],
            "api_link": "https://console.cloud.google.com/apis/library/youtube.googleapis.com"}

@router.post("/admin/youtube-setup/check")
async def admin_check(origin: str = "", admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await rs.apply_overrides(db)
    cid, sec = yt.platform_client()
    if not (cid and sec): return {"ok": False, "message": "No Google Client ID and secret are saved yet. Save the Google sign-in client (Email and calendar) or a YouTube client here, then check again."}
    ok, msg = await yt.check_client(cid, sec, (_origin(origin) if origin else settings.frontend_origin.rstrip("/")) + "/api/v1/podcasts/youtube/callback"); return {"ok": ok, "message": msg}

@router.put("/youtube/credentials")
async def save_credentials(body: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _gate(db, user)
    c = await _conn(db, user.id)
    if body.get("clear"):
        for k in ("client_id", "client_secret", "refresh_token", "channel", "email", "connected_at"): c.pop(k, None)       # back to the shared app, if there is one
    else:
        cid = str(body.get("client_id") or "").strip()[:200]; sec = str(body.get("client_secret") or "").strip()[:200]
        if cid:
            if not cid.endswith(".apps.googleusercontent.com"): raise HTTPException(422, "A Google Client ID ends in .apps.googleusercontent.com. Copy it from your Google Cloud project (APIs & Services > Credentials).")
            if cid != c.get("client_id"):                                             # a different app means a new sign-in
                for k in ("refresh_token", "channel", "email", "connected_at"): c.pop(k, None)
            c["client_id"] = cid
        if sec:
            c["client_secret"] = rs._enc(sec)
            if c.get("refresh_token") and not cid: c.pop("refresh_token", None)
        if c.get("client_id") and not c.get("client_secret"): raise HTTPException(422, "Enter the Client secret as well.")
    pr = body.get("default_privacy")
    if pr is not None:
        if pr not in yt.PRIVACY: raise HTTPException(422, "Privacy must be private, unlisted or public.")
        c["default_privacy"] = pr
    await _put(db, user.id, c)
    db.add(AuditLog(actor=user.email, action="youtube.credentials", resource_type="podcast", safe_metadata={})); await db.commit()
    return {"ok": True}

@router.post("/youtube/connect")
async def connect(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _gate(db, user); await rs.apply_overrides(db)
    c = await _conn(db, user.id); cid, sec, _ = _client(c)
    if not (cid and sec): raise HTTPException(409, "Save your Google Client ID and Client secret first (or ask an administrator to set up YouTube for everybody).")
    origin = _origin(payload.get("origin")); redirect = origin + "/api/v1/podcasts/youtube/callback"
    verifier, challenge = yt.pkce_pair(); state = uuid.uuid4().hex + uuid.uuid4().hex
    db.add(IntegrationSetting(key=f"ytstate:{state}", value={"user_id": user.id, "verifier": verifier, "redirect": redirect, "origin": origin, "at": datetime.now(timezone.utc).isoformat()}))
    await db.commit()
    return {"url": yt.auth_url(cid, redirect, state, challenge, user.email), "redirect_uri": redirect}

def _page(origin: str, ok: bool, message: str) -> HTMLResponse:
    data = json.dumps({"type": "isift-youtube", "ok": ok, "message": message}).replace("<", "\\u003c")
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><title>iSift</title><body style="font:16px system-ui;padding:32px;max-width:520px;margin:auto">
<h2>{'YouTube connected' if ok else 'YouTube was not connected'}</h2><p>{html.escape(message)}</p><p>You can close this window.</p>
<script>try{{window.opener&&window.opener.postMessage({data},{json.dumps(origin)})}}catch(e){{}};setTimeout(function(){{window.close()}},{900 if ok else 3000})</script>""")

@router.get("/youtube/callback", response_class=HTMLResponse)
async def callback(code: str = "", state: str = "", error: str = "", error_description: str = "", db: AsyncSession = Depends(get_db)):
    row = await db.get(IntegrationSetting, f"ytstate:{state}") if state else None
    if not row: return _page("null", False, "This sign-in link has expired. Close this window and try again.")
    st = dict(row.value); await db.delete(row); await db.commit(); origin = st["origin"]
    try: fresh = datetime.now(timezone.utc) - datetime.fromisoformat(st["at"]) < timedelta(minutes=15)
    except Exception: fresh = False
    if not fresh: return _page(origin, False, "This sign-in took too long. Try again.")
    if error or not code: return _page(origin, False, error_description or ("Google said: " + error if error else "Sign-in was cancelled."))
    await rs.apply_overrides(db)
    user = await db.get(User, st["user_id"])
    if not user: return _page(origin, False, "Your session was not found.")
    c = await _conn(db, user.id); cid, sec, _ = _client(c)
    try:
        tokens = await yt.exchange_code(cid, sec, code, st["redirect"], st["verifier"])
        refresh = tokens.get("refresh_token")
        if not refresh: raise yt.YouTubeError("Google did not allow continued access. Remove iSift from your Google account's connected apps (myaccount.google.com/permissions) and connect again.")
        if "youtube.upload" not in (tokens.get("scope") or ""): raise yt.YouTubeError("The YouTube upload permission was not ticked. Connect again and tick every permission box.")
        who = await yt.whoami(tokens["access_token"])
    except yt.YouTubeError as exc: return _page(origin, False, str(exc))
    c.update(refresh_token=rs._enc(refresh), channel=who["channel"], email=who["email"], connected_at=datetime.now(timezone.utc).isoformat())
    await _put(db, user.id, c)
    db.add(AuditLog(actor=user.email, action="youtube.connected", resource_type="podcast", safe_metadata={})); await db.commit()
    return _page(origin, True, f"Connected to {who['channel'] or who['email'] or 'your YouTube account'}.")

@router.delete("/youtube")
async def disconnect(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _gate(db, user)
    c = await _conn(db, user.id)
    if c.get("refresh_token"):
        try:                                                                  # ask Google to forget the permission as well
            async with yt.http(15) as h: await h.post("https://oauth2.googleapis.com/revoke", data={"token": rs._dec(c["refresh_token"])})
        except Exception: pass
    for k in ("refresh_token", "channel", "email", "connected_at"): c.pop(k, None)
    await _put(db, user.id, c)
    db.add(AuditLog(actor=user.email, action="youtube.disconnected", resource_type="podcast", safe_metadata={})); await db.commit()
    return {"ok": True}

MAX_DIRECT = 4 * 1024 ** 3

@router.post("/youtube/from-computer")
async def publish_from_computer(file: UploadFile = File(...), title: str = Form("Podcast"), description: str = Form(""), privacy: str = Form(""), tags: str = Form(""),
                                has_video: str = Form("1"), user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Post a recording that is still on the person's own computer. The file is passed on to YouTube and then deleted: nothing is kept in iSift."""
    lim = await _gate(db, user); await rs.apply_overrides(db)
    if not lim.get("youtube_post"): raise HTTPException(403, "Posting to YouTube is part of the paid plans (Standard and Business). Upgrade to post your podcasts with one click.")
    c = await _conn(db, user.id)
    if not c.get("refresh_token"): raise HTTPException(409, "YouTube is not connected yet. Connect your channel first.")
    podwork.purge()
    name = (file.content_type or "").lower(); wav = "wav" in name or (file.filename or "").lower().endswith(".wav")
    ext = "wav" if wav else "mp4" if "mp4" in name else "webm"
    dst = podwork.asset_dir(user.id) / f"yt-{uuid.uuid4().hex[:12]}.{ext}"; size = 0
    try:
        with open(dst, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DIRECT: raise HTTPException(413, "This recording is larger than 4 GB, which is too big to post from here.")
                f.write(chunk)
        if size == 0: raise HTTPException(422, "The recording was empty.")
    except BaseException:
        dst.unlink(missing_ok=True); raise
    meta = yt.clean_meta(title or "Podcast", description, privacy or c.get("default_privacy") or "private", [t.strip() for t in tags.split(",") if t.strip()])
    jid = await podwork.job_new(db, user.id, "youtube", title=meta["snippet"]["title"], privacy=meta["status"]["privacyStatus"])
    db.add(AuditLog(actor=user.email, action="youtube.post", resource_type="podcast", safe_metadata={"privacy": meta["status"]["privacyStatus"], "from": "computer"})); await db.commit()
    mime = {"wav": "audio/wav", "mp4": "video/mp4"}.get(ext, "video/webm")
    podwork.spawn(jid, _run_publish(jid, user.id, "", meta, local=dst, local_mime=mime, local_video=has_video not in ("0", "false", "")))
    return {"job_id": jid}

@router.post("/{group_id}/youtube")
async def publish(group_id: str, body: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    lim = await _gate(db, user); await rs.apply_overrides(db)
    if not lim.get("youtube_post"): raise HTTPException(403, "Posting to YouTube is part of the paid plans (Standard and Business). Upgrade to post your podcasts with one click.")
    if not lim.get("cloud_podcast"): raise HTTPException(403, "Posting to YouTube works from podcasts kept in the cloud. Your plan keeps recordings on your own computer; upgrade to Standard or Business to use it.")
    c = await _conn(db, user.id)
    if not c.get("refresh_token"): raise HTTPException(409, "YouTube is not connected yet. Open Podcast settings > YouTube and connect your channel.")
    rows = (await db.execute(select(PodcastRecording).where(PodcastRecording.group_id == group_id, PodcastRecording.owner_id == user.id))).scalars().all()
    if not rows: raise HTTPException(404, "Podcast not found")
    rec = next((r for r in rows if r.is_master), rows[0])
    meta = yt.clean_meta(str(body.get("title") or rec.title), str(body.get("description") or ""), str(body.get("privacy") or c.get("default_privacy") or "private"),
                         [t for t in (body.get("tags") or []) if isinstance(t, str)], bool(body.get("made_for_kids")))
    jid = await podwork.job_new(db, user.id, "youtube", title=meta["snippet"]["title"], privacy=meta["status"]["privacyStatus"])
    db.add(AuditLog(actor=user.email, action="youtube.post", resource_type="podcast", safe_metadata={"privacy": meta["status"]["privacyStatus"]})); await db.commit()
    podwork.spawn(jid, _run_publish(jid, user.id, rec.id, meta))
    return {"job_id": jid}

def _picture_for_sound(src: Path, dst: Path) -> bool:
    """YouTube needs a picture. A sound-only podcast gets a moving sound wave on a dark background."""
    if not shutil.which("ffmpeg"): return False
    try:
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-nostdin", "-i", str(src), "-filter_complex",
                            "[0:a]showwaves=s=1280x720:mode=cline:rate=25:colors=0x5ad1b0|0x7fb4ff,format=yuv420p[v]", "-map", "[v]", "-map", "0:a",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], capture_output=True, timeout=7200)
        return r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0
    except Exception:
        dst.unlink(missing_ok=True); return False

async def _tell_posted(name: str, email: str, meta: dict, url: str) -> tuple[bool, str]:
    """Email the person the link to the video on YouTube. Never raises: a failed email must not undo a good post."""
    if not email: return False, "your account has no email address"
    from app.services import webinars, signup
    sn = meta.get("snippet", {}); title = sn.get("title") or "your podcast"; priv = (meta.get("status") or {}).get("privacyStatus", "private")
    note = {"private": "It is private for now. To make it public, open YouTube Studio > Content, click the video, and change Visibility.",
            "unlisted": "It is unlisted: anyone with the link can watch it, but it does not appear in search."}.get(priv, "It is public.")
    body = (f"Hi {name or 'there'},\n\nYour podcast \"{title}\" has been posted to YouTube.\n\nWatch it here: {url}\n\n{note}\n"
            "YouTube can take a few minutes to finish processing before the best quality is available.\n\n— iSift")
    try: ok = bool(await webinars.send_mail(email, f"Posted to YouTube: {title}"[:150], body))
    except Exception: ok = False
    if ok: return True, ""
    return False, ("no email account is set up yet in Admin Console > Email" if not signup.app_sender() else "the mail server did not accept it, so check the Email settings in Admin Console")

async def _run_publish(jid: str, uid: str, rid: str, meta: dict, local: Path | None = None, local_mime: str = "", local_video: bool = True) -> None:
    from app.core.db import SessionLocal
    made = None
    try:
        async with SessionLocal() as db:
            rec = await db.get(PodcastRecording, rid) if rid else None; c = await _conn(db, uid); await rs.apply_overrides(db)
            owner = await db.get(User, uid); who = ((owner.display_name or "") if owner else "", (owner.email or "") if owner else "")
        cid, sec, _ = _client(c)
        await podwork.job_set(jid, message="Getting the video ready…", percent=1)
        if local: path, mime, has_video = local, local_mime or "video/webm", local_video                    # a recording sent straight from the person's computer
        else: path = await podwork.local_copy(rec); mime = rec.mimetype or "video/webm"; has_video = rec.has_video
        if not has_video:
            made = path.with_name(path.stem + "-yt.mp4")
            await podwork.job_set(jid, message="Adding a picture to your sound-only podcast…")
            if not await asyncio.to_thread(_picture_for_sound, path, made): raise yt.YouTubeError("This podcast has sound only, and a picture could not be added for YouTube.")
            path, mime = made, "video/mp4"
        token = await yt.access_token(cid, sec, rs._dec(c["refresh_token"]))
        await podwork.job_set(jid, message="Uploading to YouTube…")
        async def prog(p: int): await podwork.job_set(jid, percent=p)                 # awaited, so it can never land after the "done" note
        res = await yt.upload(token, path, meta, mime, on_progress=prog)
        await podwork.job_set(jid, message="Posted. Emailing you the link…", percent=100, url=res["url"], video_id=res["id"])
        try: emailed, why = await asyncio.wait_for(_tell_posted(who[0], who[1], meta, res["url"]), 25)         # never keeps the person waiting long
        except Exception: emailed, why = False, "the mail server took too long"
        if not emailed: log.warning("YouTube link email to %s was not sent: %s", who[1], why)
        await podwork.job_set(jid, status="done", percent=100, url=res["url"], video_id=res["id"], emailed=emailed,
                              message="Posted to YouTube." + (f" We emailed the link to {who[1]}." if emailed else f" The link could not be emailed ({why}).") + (" It is private until you make it public in YouTube Studio." if meta["status"]["privacyStatus"] == "private" else ""))
    except yt.YouTubeError as exc:
        await podwork.job_set(jid, status="error", message=str(exc))
    except Exception as exc:
        await podwork.job_set(jid, status="error", message="Posting failed: " + str(exc)[:160])
    finally:
        if made: made.unlink(missing_ok=True)
        if local: local.unlink(missing_ok=True)                                         # nothing is kept on the server
