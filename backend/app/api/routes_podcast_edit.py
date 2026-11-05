"""Podcast video editing: cut, trim, join, insert a clip inside a video, smooth the joins, record a voice-over, change a plain background.

Editing works on podcasts kept in the cloud (Standard and Business, or a Basic person the administrator has allowed), because the
work is done on the server with ffmpeg. The original is never changed: an edit is saved as a new podcast next to it.

  POST /podcasts/edit/open/{rid}      make a seekable preview of one cloud track and describe it
  POST /podcasts/edit/assets          upload a clip from the computer, a voice-over recording or a background picture (kept for a day)
  GET  /podcasts/edit/stream/...      the preview itself (signed address, supports seeking)
  POST /podcasts/edit/render          put the timeline together in the background; the result is saved as a new cloud podcast
  GET  /podcasts/jobs/{id}            progress of a render or a YouTube upload
"""
import asyncio, re, uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db, SessionLocal
from app.core.security import principal
from app.models import User, PodcastRecording, AuditLog
from app.api.routes_podcast import _gate, _mine
from app.services import podwork, videoedit as ve

router = APIRouter(prefix="/api/v1/podcasts", tags=["podcast-edit"])
KEY = re.compile(r"^[A-Za-z0-9_-]{1,24}$")

def _need_cloud(lim: dict) -> None:
    if not lim.get("podcast_edit"):
        raise HTTPException(403, "Video editing is part of the paid plans (Standard and Business). Upgrade to cut, join, add a voice-over and change the background.")
    if not lim.get("cloud_podcast"):
        raise HTTPException(403, "Editing works on podcasts kept in the cloud. Your plan keeps recordings on your own computer; upgrade to Standard or Business, or ask an administrator to allow cloud podcasts for you.")
    if not ve.have_ffmpeg(): raise HTTPException(503, "Video editing is not available on this server (ffmpeg is missing).")

def _kind(head: bytes) -> str | None:
    if head[:4] == bytes.fromhex("1A45DFA3"): return "webm"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE": return "wav"
    if head[4:8] == b"ftyp": return "mp4"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"): return "mp3"
    if head[:4] == b"OggS": return "ogg"
    if head[:4] == b"fLaC": return "flac"
    if head[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if head[:3] == b"\xff\xd8\xff": return "jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return "webp"
    return None

@router.post("/edit/open/{rid}")
async def open_for_edit(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    lim = await _gate(db, user); _need_cloud(lim)
    r = await _mine(db, rid, user)
    podwork.purge()
    try: path = await podwork.local_copy(r)
    except Exception as exc: raise HTTPException(502, "The recording could not be opened: " + str(exc)[:160])
    try: info = await asyncio.to_thread(ve.probe, path)
    except ve.EditError as exc: raise HTTPException(422, str(exc))
    return {"kind": "rec", "id": r.id, "label": r.label, "title": r.title, "url": podwork.sign("rec", r.id), **info}

@router.post("/edit/assets")
async def add_asset(file: UploadFile = File(...), kind: str = Form("clip"), user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    lim = await _gate(db, user); _need_cloud(lim)
    if kind not in podwork.ASSET_KINDS: raise HTTPException(422, "Unknown kind of file.")
    podwork.purge()
    aid = uuid.uuid4().hex[:20]; d = podwork.asset_dir(user.id); tmp = d / f"{aid}.part"; size, head = 0, b""
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > podwork.MAX_ASSET_BYTES: raise HTTPException(413, "This file is larger than 2 GB.")
                if not head: head = chunk[:16]
                out.write(chunk)
        ext = _kind(head)
        if not ext or (kind == "image" and ext not in ("png", "jpg", "webp")) or (kind != "image" and ext in ("png", "jpg", "webp")):
            raise HTTPException(415, "That file type cannot be used here. Use an MP4 or WebM video, a WAV, MP3 or OGG sound, or a PNG or JPG picture for a background.")
        final = d / f"{aid}.{ext}"
        if ext == "webm" and kind != "image":
            if not await asyncio.to_thread(ve.remux, tmp, final.with_name(final.name + ".part"), "webm"): tmp.replace(final)
            else: final.with_name(final.name + ".part").replace(final); tmp.unlink(missing_ok=True)
        else: tmp.replace(final)
    except BaseException:
        tmp.unlink(missing_ok=True); raise
    info = {"duration": 0.0, "has_video": True, "has_audio": False, "width": 0, "height": 0}
    if kind != "image":
        try: info = await asyncio.to_thread(ve.probe, final)
        except ve.EditError as exc: final.unlink(missing_ok=True); raise HTTPException(422, str(exc))
    return {"kind": "asset", "id": aid, "label": (file.filename or "clip")[:60], "url": podwork.sign("asset", aid), "asset_kind": kind, **info}

@router.get("/edit/stream/{kind}/{ident}")
async def stream(kind: str, ident: str, exp: int = Query(0), sig: str = Query("")):
    """The preview file. The address carries its own signature, so a video tag can play it; Range requests (seeking) are supported."""
    if kind not in ("rec", "asset") or not podwork.verify(kind, ident, exp, sig): raise HTTPException(403, "This preview address has expired. Reopen the video.")
    p = podwork.proxy_path(ident) if kind == "rec" else podwork.find_asset(ident)
    if not p or not p.is_file(): raise HTTPException(410, "The preview is no longer available. Reopen the video.")
    mt = {"webm": "video/webm", "mp4": "video/mp4", "wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg", "flac": "audio/flac", "png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}.get(p.suffix.lstrip("."), "application/octet-stream")
    return FileResponse(p, media_type=mt)

def _num(v, lo: float, hi: float, name: str, default: float = 0.0) -> float:
    try: x = float(v if v is not None else default)
    except (TypeError, ValueError): raise HTTPException(422, f"{name} must be a number.")
    if x != x or x < lo or x > hi: raise HTTPException(422, f"{name} must be between {lo:g} and {hi:g}.")
    return x

@router.post("/edit/render")
async def start_render(body: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """body: {title, sources:{key:{kind:'rec'|'asset', id}}, segments:[{source,start,end}], crossfade, fade_in, fade_out,
    voiceovers:[{source,at,gain}], original_volume, background:{mode,key_color,similarity,color,image}, polish, height}"""
    lim = await _gate(db, user); _need_cloud(lim)
    srcs = body.get("sources") or {}
    if not isinstance(srcs, dict) or not srcs or len(srcs) > 40: raise HTTPException(422, "No clips were given.")
    refs: dict[str, tuple[str, str]] = {}
    for k, v in srcs.items():
        if not KEY.match(str(k)) or not isinstance(v, dict) or v.get("kind") not in ("rec", "asset") or not isinstance(v.get("id"), str): raise HTTPException(422, "A clip is not valid.")
        refs[k] = (v["kind"], v["id"])
    segs = []
    for s in (body.get("segments") or []):
        if not isinstance(s, dict) or s.get("source") not in refs: raise HTTPException(422, "A piece of the timeline points at a clip that is not there.")
        a, b = _num(s.get("start"), 0, 86400, "Start"), _num(s.get("end"), 0, 86400, "End")
        segs.append(ve.Segment(s["source"], round(a, 3), round(b, 3)))
    vos = []
    for v in (body.get("voiceovers") or []):
        if not isinstance(v, dict) or v.get("source") not in refs: raise HTTPException(422, "A voice-over points at a file that is not there.")
        vos.append(ve.VoiceOver(v["source"], _num(v.get("at"), 0, 86400, "Voice-over time"), _num(v.get("gain"), 0, 3, "Voice-over volume", 1.0)))
    bgd = body.get("background") if isinstance(body.get("background"), dict) else None
    bg = None
    if bgd and bgd.get("mode") in ("color", "image"):
        bg = ve.Background(bgd["mode"], str(bgd.get("key_color") or "00ff00"), _num(bgd.get("similarity"), 0.05, 0.6, "Similarity", 0.25), str(bgd.get("color") or "1b2a41"), str(bgd.get("image") or ""))
        if bg.mode == "image" and bg.image not in refs: raise HTTPException(422, "The background picture was not given.")
    plan = ve.Plan(segs, _num(body.get("crossfade"), 0, ve.XFADE_MAX, "Crossfade"), _num(body.get("fade_in"), 0, ve.FADE_MAX, "Fade in"), _num(body.get("fade_out"), 0, ve.FADE_MAX, "Fade out"),
                   vos, _num(body.get("original_volume"), 0, 2, "Original volume", 1.0), bg, bool(body.get("polish")), str(body.get("height") or "source"))
    # every clip must be the person's own
    recs: dict[str, PodcastRecording] = {}
    for k, (kind, ident) in refs.items():
        if kind == "rec": recs[k] = await _mine(db, ident, user)
        else:
            p = podwork.find_asset(ident)
            if not p or p.parent.name != podwork.asset_dir(user.id).name: raise HTTPException(404, "An uploaded clip has expired. Add it again.")
    first = next((recs[s.source] for s in segs if s.source in recs), None)
    title = (str(body.get("title") or "").strip() or ((first.title + " (edited)") if first else "Edited podcast"))[:200]
    jid = await podwork.job_new(db, user.id, "edit", title=title)
    podwork.spawn(jid, _run_render(jid, user.id, user.email, plan, refs, title))
    return {"job_id": jid}

async def _run_render(jid: str, uid: str, email: str, plan: ve.Plan, refs: dict[str, tuple[str, str]], title: str) -> None:
    from app.services import entitlements as ent, storage
    out = None
    try:
        async with SessionLocal() as db:
            user = await db.get(User, uid)
            await podwork.job_set(jid, message="Getting the videos ready…")
            files: dict[str, Path] = {}
            for k, (kind, ident) in refs.items():
                if kind == "rec":
                    r = await db.get(PodcastRecording, ident)
                    if not r or r.owner_id != uid: raise ve.EditError("A video on the timeline was deleted.")
                    files[k] = await podwork.local_copy(r)
                else:
                    p = podwork.find_asset(ident)
                    if not p: raise ve.EditError("An uploaded clip has expired. Add it again.")
                    files[k] = p
            gid, rid = str(uuid.uuid4()), str(uuid.uuid4())
            base = Path(settings.audio_storage_dir) / "podcasts"; base.mkdir(parents=True, exist_ok=True)
            out = base / f"{rid}.mp4"
            await podwork.job_set(jid, message="Putting the video together…")
            loop = asyncio.get_running_loop(); last = [0]
            def prog(pct: int):
                if pct - last[0] >= 3: last[0] = pct; asyncio.run_coroutine_threadsafe(podwork.job_set(jid, percent=pct), loop).result(30)       # waits, so it can never land after the "done" note
            res = await asyncio.to_thread(ve.render, plan, files, out, 7200, prog)
            await ent.check_storage(db, user, res["size_bytes"])
            await podwork.job_set(jid, percent=99, message="Saving…")
            try: placed = await storage.store_file(out, user, rid, True, keep_original=True, mime_in="video/mp4")
            except Exception as exc: raise ve.EditError("The edited video could not be saved to cloud storage: " + str(exc)[:160])
            size2 = placed.pop("size_bytes")
            db.add(PodcastRecording(id=rid, group_id=gid, owner_id=uid, title=title, label="Master", is_master=True, has_video=True, width=res["width"], height=res["height"],
                                    duration_s=int(round(res["duration"])), audio_kbps=192, size_bytes=size2, **placed))
            db.add(AuditLog(actor=email, action="podcast.edited", resource_type="podcast", safe_metadata={"pieces": len(plan.segments), "voiceovers": len(plan.voiceovers), "seconds": int(res["duration"])}))
            await db.commit()
        await podwork.job_set(jid, status="done", percent=100, message="Your edited video is saved as a new podcast.", group_id=gid, duration=res["duration"])
    except ve.EditError as exc:
        if out: out.unlink(missing_ok=True)
        await podwork.job_set(jid, status="error", message=str(exc))
    except Exception as exc:
        if out: out.unlink(missing_ok=True)
        await podwork.job_set(jid, status="error", message="The edit failed: " + str(exc)[:160])

@router.get("/jobs/{jid}")
async def job(jid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    j = await podwork.job_get(db, jid, user.id)
    if not j: raise HTTPException(404, "That task was not found.")
    return j
