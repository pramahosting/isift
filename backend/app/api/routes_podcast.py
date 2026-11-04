"""HD podcast recording.

The recording itself is made in the person's browser (Podcast Studio): studio-quality audio and up to 4K video, with one separate
track per microphone as well as the mixed master. Where it is kept is the person's choice, within their plan:

  * on their own computer: the browser saves the file; nothing is sent here. This is the only choice on the Basic plan.
  * in the cloud: the browser uploads it here (Standard and Business, when the plan's cloud podcast switch is on).

Cloud files keep their original quality: they are never re-encoded."""
import asyncio, shutil, uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal
from app.models import User, PodcastRecording, AuditLog

router = APIRouter(prefix="/api/v1/podcasts", tags=["podcast"])
MODULE = "podcast"
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_TRACKS = 8
WEBM = bytes.fromhex("1A45DFA3")

# What the studio asks the browser for: the best a browser can record. The browser uses the best its devices and computer can deliver.
QUALITY = {"audio_sample_rate": 48000, "audio_channels": 2, "audio_kbps": 256, "lossless_wav": True,
           "video_ideal": {"width": 3840, "height": 2160, "fps": 30}, "video_fallback": {"width": 1920, "height": 1080, "fps": 30},
           "video_mbps": {"2160": 20, "1440": 12, "1080": 8, "720": 5}}

async def _gate(db: AsyncSession, user: User) -> dict:
    from app.api import routes_modules as mods
    from app.services import entitlements as ent
    if MODULE in await mods.disabled(db): raise HTTPException(403, "Podcast Studio is switched off by your administrator.")
    lim = await ent.limits(db, user)
    if not lim.get("podcast"): raise HTTPException(403, "Podcast recording is not included in your plan. Ask an administrator to allow it for you.")
    return lim

def _sniff(head: bytes) -> str | None:
    if head[:4] == WEBM: return "webm"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE": return "wav"
    return None

async def _save(f: UploadFile, dest: Path) -> tuple[int, str]:
    size, head = 0, b""
    try:
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_BYTES: raise HTTPException(413, "This file is larger than the 2 GB allowed for one track. Record a shorter session or at a lower resolution.")
                if not head: head = chunk[:12]
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True); raise
    kind = _sniff(head)
    if not kind: dest.unlink(missing_ok=True); raise HTTPException(415, "The file is not a WebM or WAV recording.")
    return size, kind

def _view(r: PodcastRecording) -> dict:
    return {"id": r.id, "group_id": r.group_id, "title": r.title, "label": r.label, "is_master": r.is_master, "has_video": r.has_video, "width": r.width, "height": r.height,
            "duration_s": r.duration_s, "audio_kbps": r.audio_kbps, "size_bytes": r.size_bytes, "mimetype": r.mimetype, "storage": r.storage,
            "created_at": (r.created_at.isoformat() if r.created_at else "")}

@router.get("/config")
async def config(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    from app.services import storage
    lim = await _gate(db, user)
    cloud = bool(lim.get("cloud_podcast"))
    return {"allowed": True, "cloud_allowed": cloud, "default_destination": "local",
            "cloud_note": "" if cloud else "Your plan saves podcast recordings on this computer. Upgrade to Standard or Business to also keep them in the cloud.",
            "cloud_storage": "r2" if storage.configured() else "database", "max_file_mb": MAX_FILE_BYTES // (1024 * 1024), "max_tracks": MAX_TRACKS, "quality": QUALITY}

@router.post("")
async def save_podcast(title: str = Form(""), duration_s: int = Form(0), width: int = Form(0), height: int = Form(0), audio_kbps: int = Form(0),
                       track_labels: list[str] = Form([]), master: UploadFile = File(...), tracks: list[UploadFile] = File([]),
                       user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Keep a finished podcast in the cloud. Plans without cloud podcast recording are refused: their recordings stay on the person's own computer."""
    from app.services import entitlements as ent, storage
    lim = await _gate(db, user)
    if not lim.get("cloud_podcast"): raise HTTPException(403, "Your plan keeps podcast recordings on your own computer only. Upgrade to Standard or Business to store them in the cloud.")
    if len(tracks) > MAX_TRACKS: raise HTTPException(400, f"At most {MAX_TRACKS} separate tracks.")
    gid = str(uuid.uuid4()); base = Path(settings.audio_storage_dir) / "podcasts"; base.mkdir(parents=True, exist_ok=True)
    items: list[tuple[UploadFile, str, bool]] = [(master, "Master", True)] + [(t, (track_labels[i] if i < len(track_labels) else f"Track {i + 1}")[:80] or f"Track {i + 1}", False) for i, t in enumerate(tracks)]
    saved: list[tuple[Path, int, str, str, bool, str]] = []
    try:
        total = 0
        for f, label, is_master in items:
            rid = str(uuid.uuid4()); dest = base / f"{rid}.tmp"
            size, kind = await _save(f, dest); total += size
            saved.append((dest, size, kind, label, is_master, rid))
        await ent.check_storage(db, user, total)
        has_video = bool(width and height)
        rows = []
        for dest, size, kind, label, is_master, rid in saved:
            vid = has_video and is_master and kind == "webm"
            mime = "audio/wav" if kind == "wav" else ("video/webm" if vid else "audio/webm")
            final = base / f"{rid}.{'wav' if kind == 'wav' else 'webm'}"; dest.replace(final)
            try: placed = await storage.store_file(final, user, rid, vid, keep_original=True, mime_in=mime)
            except Exception as exc:
                raise HTTPException(502, "The podcast could not be saved to cloud storage: " + str(exc)[:160] + " Your own computer's copy is not affected.")
            size2 = placed.pop("size_bytes")
            rows.append(PodcastRecording(id=rid, group_id=gid, owner_id=user.id, title=(title or "Podcast")[:200], label=label, is_master=is_master, has_video=vid,
                                         width=width if vid else 0, height=height if vid else 0, duration_s=max(0, duration_s), audio_kbps=max(0, audio_kbps), size_bytes=size2, **placed))
        for r in rows: db.add(r)
        db.add(AuditLog(actor=user.email, action="podcast.saved", resource_type="podcast", safe_metadata={"tracks": len(rows)}))
        await db.commit()
    except Exception:
        for dest, *_ in saved: dest.unlink(missing_ok=True)
        raise
    return {"group_id": gid, "tracks": len(saved), "message": "Podcast saved in the cloud at its original quality. You can download it any time from Podcast Studio."}

@router.get("")
async def my_podcasts(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _gate(db, user)
    rows = (await db.execute(select(PodcastRecording).where(PodcastRecording.owner_id == user.id).order_by(PodcastRecording.created_at.desc()).limit(300))).scalars().all()
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(r.group_id, {"group_id": r.group_id, "title": r.title, "created_at": _view(r)["created_at"], "tracks": []})
        g["tracks"].append(_view(r))
    for g in groups.values(): g["tracks"].sort(key=lambda t: (not t["is_master"], t["label"]))
    return list(groups.values())

async def _mine(db, rid: str, user: User) -> PodcastRecording:
    r = await db.get(PodcastRecording, rid)
    if not r or r.owner_id != user.id: raise HTTPException(404, "Recording not found")
    return r

def _name(r: PodcastRecording) -> str:
    safe = "".join(c if c.isalnum() or c in " .-_" else "_" for c in f"{r.title} {r.label}").strip()[:80] or "podcast"
    return safe + (".wav" if r.mimetype == "audio/wav" else ".webm")

@router.get("/{rid}/file")
async def podcast_file(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _gate(db, user)
    r = await _mine(db, rid, user)
    head = {"Content-Disposition": f'attachment; filename="{_name(r)}"'}
    if r.storage == "r2":
        from app.services import storage
        try: obj = storage.client().get_object(Bucket=settings.r2_bucket, Key=r.object_key)
        except Exception: raise HTTPException(502, "Cloud storage could not be reached. Try again shortly.")
        return StreamingResponse(obj["Body"].iter_chunks(1024 * 1024), media_type=r.mimetype or "audio/webm", headers={**head, "Content-Length": str(obj["ContentLength"])})
    if r.storage == "database":
        blob = (await db.execute(select(PodcastRecording.data).where(PodcastRecording.id == rid))).scalar_one_or_none()
        if not blob: raise HTTPException(410, "This recording is no longer stored.")
        return Response(bytes(blob), media_type=r.mimetype or "audio/webm", headers=head)
    p = Path(r.path)
    if not p.is_file(): raise HTTPException(410, "The recording file is no longer in the recordings folder.")
    return FileResponse(p, media_type=r.mimetype or "audio/webm", filename=_name(r), content_disposition_type="attachment")

@router.delete("/{group_id}")
async def delete_podcast(group_id: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PodcastRecording).where(PodcastRecording.group_id == group_id, PodcastRecording.owner_id == user.id))).scalars().all()
    if not rows: raise HTTPException(404, "Recording not found")
    from app.services import storage
    for r in rows:
        if r.storage == "r2" and r.object_key: await asyncio.to_thread(storage.delete_object, r.object_key)
        elif r.path: Path(r.path).unlink(missing_ok=True)
        await db.delete(r)
    db.add(AuditLog(actor=user.email, action="podcast.deleted", resource_type="podcast", safe_metadata={})); await db.commit()
    return {"ok": True}
