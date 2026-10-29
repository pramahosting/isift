"""Docs > Media Converter. Pictures are converted on the spot. Videos are stored only in Cloudflare R2 (blob storage): the upload and the converted file, never in the database."""
import asyncio, logging, tempfile, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from app.core.security import principal
from app.models import User
from app.core.db import get_db
from app.services import media, store, storage
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/media", tags=["media"])
log = logging.getLogger("isift")
IMAGE_LIMIT = 200 * 1024 * 1024
VIDEO_LIMIT = 4 * 1024 * 1024 * 1024
KEEP_SECONDS = 3 * 86400
JOBS: dict[str, dict] = {}                  # running / just-finished conversions (the finished list itself is kept in the person's record)
_slots = asyncio.Semaphore(2)

def _key(email): return store.hkey("media", email)

async def _receive(request: Request, limit: int) -> tuple[Path, int]:
    tmp = Path(tempfile.mkdtemp(prefix="media_")) / "in.bin"; n = 0
    with tmp.open("wb") as f:
        async for chunk in request.stream():
            n += len(chunk)
            if n > limit: f.close(); shutil.rmtree(tmp.parent, ignore_errors=True); raise HTTPException(413, "That file is too large.")
            f.write(chunk)
    if n == 0: raise HTTPException(400, "The file was empty.")
    return tmp, n
import shutil

@router.get("/status")
async def status(user: User = Depends(principal)):
    return {"r2": storage.configured(), "ffmpeg": bool(shutil.which("ffmpeg")), "image_in": sorted(media.IMAGE_IN), "image_out": list(media.IMAGE_OUT), "video_in": sorted(media.VIDEO_IN), "video_out": list(media.VIDEO_OUT), "compress": list(media.COMPRESS)}

@router.post("/image")
async def image(request: Request, filename: str, to: str, user: User = Depends(principal)):
    to = to.lower().lstrip(".")
    path, n = await _receive(request, IMAGE_LIMIT)
    try:
        data = path.read_bytes()
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    try: out, mime = await asyncio.to_thread(media.convert_image, data, to, filename)
    except media.MediaError as e: raise HTTPException(422, str(e))
    stem = Path(filename).stem[:80] or "picture"
    return Response(out, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{stem}.{to}"', "X-Filename": f"{stem}.{to}", "Access-Control-Expose-Headers": "X-Filename"})

async def _run(job: dict, user_email: str, src: Path, to: str, quality: str = "balanced"):
    from app.core.db import SessionLocal
    d = src.parent; oext = media.out_ext(to); out = d / f"out.{oext}"
    try:
        async with _slots:
            job["state"] = "converting"
            await asyncio.to_thread(media.convert_video, src, out, to, lambda f: job.__setitem__("progress", round(f, 3)), quality=quality)
        job["state"] = "saving"
        out_key = f"{storage.top_folder()}/media/{job['id']}/{job['stem']}{'-compressed' if to in media.COMPRESS else ''}.{oext}"
        await asyncio.to_thread(storage._put, out, out_key, media.VIDEO_OUT[to])
        job.update(state="done", progress=1.0, out_key=out_key, out_size=out.stat().st_size, out_name=f"{job['stem']}{'-compressed' if to in media.COMPRESS else ''}.{oext}")
        async with SessionLocal() as db:
            rec = await store.get(db, _key(user_email), {"items": []})
            rec["items"] = [{k: job[k] for k in ("id", "name", "to", "in_key", "out_key", "out_name", "out_size", "at")}] + [i for i in rec.get("items", []) if i["id"] != job["id"]]
            await store.put(db, _key(user_email), rec)
    except media.MediaError as e: job.update(state="error", error=str(e))
    except Exception as e:
        log.exception("Video conversion failed"); job.update(state="error", error="The conversion could not be completed. Please try again.")
    finally:
        shutil.rmtree(d, ignore_errors=True)         # the temporary working copy on the server; the stored copies are in blob storage

@router.post("/video")
async def video(request: Request, filename: str, to: str, quality: str = "balanced", user: User = Depends(principal)):
    to = to.lower().lstrip(".")
    if to not in media.VIDEO_OUT: raise HTTPException(400, "That output format is not available.")
    if not storage.configured(): raise HTTPException(409, "Videos are kept only in blob storage, and it is not set up yet. An administrator can set up Cloudflare R2 in Admin Console, API and Settings.")
    if not shutil.which("ffmpeg"): raise HTTPException(409, "Video conversion is not available on this server.")
    src, n = await _receive(request, VIDEO_LIMIT)
    jid = uuid.uuid4().hex[:16]; stem = (Path(filename).stem[:80] or "video").replace("/", "_")
    job = {"id": jid, "owner": user.email, "name": Path(filename).name[:200], "stem": stem, "to": to, "state": "saving", "progress": 0.0, "at": time.time()}
    JOBS[jid] = job
    try:        # the upload itself goes to blob storage first
        in_key = f"{storage.top_folder()}/media/{jid}/{stem}-original.{media.ext(filename) or 'bin'}"
        await asyncio.to_thread(storage._put, src, in_key, request.headers.get("content-type") or "application/octet-stream")
        job["in_key"] = in_key
    except Exception:
        shutil.rmtree(src.parent, ignore_errors=True); JOBS.pop(jid, None)
        raise HTTPException(502, "The upload could not be saved to blob storage. Check the R2 settings in Admin Console.")
    asyncio.create_task(_run(job, user.email, src, to, quality if quality in media.QUALITY else "balanced"))
    return {"id": jid}

def _public(j: dict) -> dict:
    return {k: j.get(k) for k in ("id", "name", "to", "state", "progress", "error", "out_name", "out_size", "at")}

@router.get("/jobs")
async def jobs(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rec = await store.get(db, _key(user.email), {"items": []}); now = time.time(); keep = []; gone = []
    for i in rec.get("items", []):
        (keep if now - i.get("at", now) < KEEP_SECONDS else gone).append(i)
    for i in gone:                                       # converted files and uploads are removed after 3 days
        for k in (i.get("in_key"), i.get("out_key")):
            if k: await asyncio.to_thread(storage.delete_object, k)
    if gone: rec["items"] = keep; await store.put(db, _key(user.email), rec)
    live = [_public(j) for j in JOBS.values() if j["owner"] == user.email and j["state"] != "done"]
    done = [{"id": i["id"], "name": i["name"], "to": i["to"], "state": "done", "progress": 1.0, "out_name": i["out_name"], "out_size": i["out_size"], "at": i["at"]} for i in keep]
    return {"items": sorted(live + done, key=lambda x: -x.get("at", 0))}

async def _mine(db, user, jid):
    rec = await store.get(db, _key(user.email), {"items": []})
    i = next((x for x in rec.get("items", []) if x["id"] == jid), None)
    if not i: raise HTTPException(404, "That file was not found. Converted videos are kept for 3 days.")
    return rec, i

@router.get("/{jid}/url")
async def download_url(jid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    _, i = await _mine(db, user, jid)
    try: url = await asyncio.to_thread(storage.presigned_url, i["out_key"], i["out_name"], media.VIDEO_OUT.get(i["to"], "application/octet-stream"), 900)
    except Exception: raise HTTPException(502, "Blob storage could not be reached.")
    return {"url": url, "name": i["out_name"]}

@router.delete("/{jid}")
async def delete(jid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rec, i = await _mine(db, user, jid)
    for k in (i.get("in_key"), i.get("out_key")):
        if k: await asyncio.to_thread(storage.delete_object, k)
    rec["items"] = [x for x in rec["items"] if x["id"] != jid]; await store.put(db, _key(user.email), rec); JOBS.pop(jid, None)
    return {"ok": True}
