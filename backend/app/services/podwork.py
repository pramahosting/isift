"""Working files for Podcast Studio editing and publishing: seekable copies of recordings, uploaded clips and voice-overs, signed
preview addresses and the small job records the browser polls. Working files are temporary; they are deleted after a day."""
import asyncio, hashlib, hmac, shutil, time, uuid
from pathlib import Path
from app.core.config import settings

KEEP_SECONDS = 24 * 3600
ASSET_KINDS = ("clip", "voice", "image")
MAX_ASSET_BYTES = 2 * 1024 * 1024 * 1024

def root() -> Path:
    p = Path(settings.audio_storage_dir) / "podcasts" / "work"
    p.mkdir(parents=True, exist_ok=True); return p

def proxy_dir() -> Path:
    p = root() / "proxy"; p.mkdir(parents=True, exist_ok=True); return p

def asset_dir(owner_id: str) -> Path:
    safe = "".join(c for c in owner_id if c.isalnum() or c == "-")[:40] or "x"
    p = root() / "assets" / safe; p.mkdir(parents=True, exist_ok=True); return p

def purge() -> None:
    """Remove working files older than a day."""
    cut = time.time() - KEEP_SECONDS
    try:
        for p in root().rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cut: p.unlink()
            except OSError: pass
    except OSError: pass

# ---- signed preview addresses: a <video> tag cannot send a sign-in header, so the address itself carries a short-lived signature ----
def _sig(kind: str, ident: str, exp: int) -> str:
    return hmac.new(settings.local_auth_secret.encode(), f"{kind}:{ident}:{exp}".encode(), hashlib.sha256).hexdigest()

def sign(kind: str, ident: str, seconds: int = 3 * 3600) -> str:
    exp = int(time.time()) + seconds
    return f"/api/v1/podcasts/edit/stream/{kind}/{ident}?exp={exp}&sig={_sig(kind, ident, exp)}"

def verify(kind: str, ident: str, exp: int, sig: str) -> bool:
    return exp > time.time() and hmac.compare_digest(_sig(kind, ident, exp), sig or "")

def find_asset(ident: str) -> Path | None:
    if not ident.isalnum(): return None
    for p in (root() / "assets").glob(f"*/{ident}.*"): return p
    return None

def proxy_path(rid: str) -> Path | None:
    for p in proxy_dir().glob(f"{rid}.*"):
        if p.suffix not in (".part", ".raw"): return p
    return None

# ---- jobs: a record the browser polls while a long task (an edit, a YouTube upload) runs ----
JOBS: dict[str, asyncio.Task] = {}          # keeps a reference so a running task is not collected

async def job_new(db, user_id: str, kind: str, **extra) -> str:
    from app.models import IntegrationSetting
    jid = uuid.uuid4().hex[:16]
    db.add(IntegrationSetting(key=f"podjob:{jid}", value={"user_id": user_id, "kind": kind, "status": "working", "percent": 0, "message": "", **extra}))
    await db.commit(); return jid

async def job_set(jid: str, **fields) -> None:
    from app.core.db import SessionLocal
    from app.models import IntegrationSetting
    async with SessionLocal() as db:
        row = await db.get(IntegrationSetting, f"podjob:{jid}")
        if row: row.value = {**row.value, **fields}; await db.commit()

async def job_get(db, jid: str, user_id: str) -> dict | None:
    from app.models import IntegrationSetting
    row = await db.get(IntegrationSetting, f"podjob:{jid}")
    if not row or row.value.get("user_id") != user_id: return None
    return {k: v for k, v in row.value.items() if k != "user_id"} | {"id": jid}

def spawn(jid: str, coro) -> None:
    t = asyncio.create_task(coro); JOBS[jid] = t
    t.add_done_callback(lambda _t: JOBS.pop(jid, None))

async def local_copy(rec) -> Path:
    """A seekable file on this server for a recording (downloaded from cloud storage when needed). Browser WebM files have no length
    in their header, so they are copied once without re-encoding (nothing is lost) to give them one."""
    from app.core.db import SessionLocal
    from sqlalchemy import select
    from app.models import PodcastRecording
    from app.services import storage, videoedit
    have = proxy_path(rec.id)
    if have: return have
    d = proxy_dir(); ext = "wav" if rec.mimetype == "audio/wav" else ("mp4" if rec.mimetype == "video/mp4" else "webm")
    raw = d / f"{rec.id}.raw"; final = d / f"{rec.id}.{ext}"
    if rec.storage == "r2":
        await asyncio.to_thread(storage.client().download_file, settings.r2_bucket, rec.object_key, str(raw))
    elif rec.storage == "database":
        async with SessionLocal() as db:
            blob = (await db.execute(select(PodcastRecording.data).where(PodcastRecording.id == rec.id))).scalar_one_or_none()
        if not blob: raise RuntimeError("This recording is no longer stored.")
        raw.write_bytes(bytes(blob))
    else:
        p = Path(rec.path)
        if not p.is_file(): raise RuntimeError("The recording file is no longer in the recordings folder.")
        await asyncio.to_thread(shutil.copyfile, p, raw)
    if ext == "webm":
        ok = await asyncio.to_thread(videoedit.remux, raw, final.with_name(final.name + ".part"), "webm")
        if ok: final.with_name(final.name + ".part").replace(final); raw.unlink(missing_ok=True)
        else: raw.replace(final)
    else: raw.replace(final)
    return final
