"""Recording storage: Cloudflare R2 (or any S3-compatible bucket) when set up in Admin Console,
otherwise the database (blob) for modest files, otherwise the local data folder.
Settings are read live from `settings`, so a change in Admin takes effect on the next recording."""
import asyncio, shutil, subprocess, tempfile, uuid
from pathlib import Path
from app.core.config import settings

REQUIRED = ("r2_endpoint", "r2_access_key_id", "r2_secret_access_key", "r2_bucket")
DB_BLOB_LIMIT = 150 * 1024 * 1024          # bigger files than this are not put in the database
TRANSCODE_LIMIT = 300 * 1024 * 1024

def configured() -> bool:
    return all(getattr(settings, k, "") for k in REQUIRED)

def missing() -> list[str]:
    names = {"r2_endpoint": "Endpoint address", "r2_access_key_id": "Access key ID", "r2_secret_access_key": "Secret access key", "r2_bucket": "Bucket name"}
    return [names[k] for k in REQUIRED if not getattr(settings, k, "")]

def _endpoint() -> str:
    e = settings.r2_endpoint.strip().rstrip("/")
    return e if e.startswith("http") else "https://" + e

def client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=_endpoint(), aws_access_key_id=settings.r2_access_key_id, aws_secret_access_key=settings.r2_secret_access_key,
                        region_name="auto", config=Config(signature_version="s3v4", retries={"max_attempts": 3}, connect_timeout=10, read_timeout=60))

TOP_FOLDER = "isift-video"

def top_folder() -> str:
    return (settings.r2_prefix or TOP_FOLDER).strip("/") or TOP_FOLDER

def account_folder(user) -> str:
    """One folder per account, readable and permanent: <email name>-<first 8 of the account id>. The id part never changes and keeps two people with the same email name apart."""
    label = "".join(c if c.isalnum() else "_" for c in (user.email or "user").split("@")[0]).strip("_")[:40] or "user"
    return f"{label}-{str(user.id).replace('-', '')[:8]}"

def make_key(user, rid: str, ext: str) -> str:
    return f"{top_folder()}/{account_folder(user)}/{rid}.{ext}"

def transcode_mp4(src: Path, dst: Path, timeout: int = 600) -> bool:
    """Smaller, universally playable file. Returns False (and the original is kept) if ffmpeg is missing or fails."""
    if not shutil.which("ffmpeg") or src.stat().st_size > TRANSCODE_LIMIT: return False
    try:
        r = subprocess.run(["ffmpeg", "-y", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(dst)], capture_output=True, timeout=timeout)
        return r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0
    except Exception:
        dst.unlink(missing_ok=True); return False

def _put(path: Path, key: str, mime: str):
    client().upload_file(str(path), settings.r2_bucket, key, ExtraArgs={"ContentType": mime})

async def store_file(path: Path, owner, rid: str, has_video: bool) -> dict:
    """Move one recording file to its permanent home. Returns fields for RoomRecording."""
    size = path.stat().st_size
    if configured():
        out, mime, ext = path, ("video/webm" if has_video else "audio/webm"), "webm"
        if has_video:
            mp4 = path.with_suffix(".mp4")
            if await asyncio.to_thread(transcode_mp4, path, mp4): out, mime, ext = mp4, "video/mp4", "mp4"
        key = make_key(owner, rid, ext)
        await asyncio.to_thread(_put, out, key, mime)
        size = out.stat().st_size
        if out != path: out.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        return {"storage": "r2", "object_key": key, "mimetype": mime, "size_bytes": size, "path": "", "data": None}
    if size <= DB_BLOB_LIMIT:
        data = path.read_bytes(); path.unlink(missing_ok=True)
        return {"storage": "database", "object_key": None, "mimetype": "video/webm" if has_video else "audio/webm", "size_bytes": size, "path": "", "data": data}
    return {"storage": "file", "object_key": None, "mimetype": "video/webm" if has_video else "audio/webm", "size_bytes": size, "path": str(path), "data": None}

def presigned_url(key: str, filename: str, mime: str, seconds: int = 900) -> str:
    safe = filename.replace('"', "")
    return client().generate_presigned_url("get_object", Params={"Bucket": settings.r2_bucket, "Key": key, "ResponseContentType": mime,
                                           "ResponseContentDisposition": f'inline; filename="{safe}"'}, ExpiresIn=seconds)

def delete_object(key: str) -> bool:
    try: client().delete_object(Bucket=settings.r2_bucket, Key=key); return True
    except Exception: return False

async def test_r2() -> dict:
    if not configured(): return {"configured": False, "status": "not_configured", "detail": "Not set up. Recordings are kept in the database instead. Still needed: " + ", ".join(missing()) + "."}
    def probe():
        c = client(); c.head_bucket(Bucket=settings.r2_bucket)
        key = f"{top_folder()}/_connection_test_{uuid.uuid4().hex[:8]}.txt"
        c.put_object(Bucket=settings.r2_bucket, Key=key, Body=b"iSift storage test"); c.delete_object(Bucket=settings.r2_bucket, Key=key)
    try:
        await asyncio.to_thread(probe)
        return {"configured": True, "status": "connected", "detail": f"Connected to bucket \"{settings.r2_bucket}\": a test file was written and removed."}
    except ImportError:
        return {"configured": True, "status": "failed", "detail": "The server is missing the boto3 package. Run: pip install boto3"}
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
        hint = {"403": "The keys were accepted but cannot write to this bucket. Give the API token Object Read & Write permission.", "AccessDenied": "The keys cannot write to this bucket. Give the API token Object Read & Write permission.",
                "404": "Bucket not found. Check the bucket name.", "NoSuchBucket": "Bucket not found. Check the bucket name.", "InvalidAccessKeyId": "Access key ID not recognised.", "SignatureDoesNotMatch": "Secret access key is wrong."}.get(code)
        return {"configured": True, "status": "failed", "detail": hint or f"{type(e).__name__}: {str(e)[:180]}"}


BASIC_DAYS = 2

async def purge_expired(db) -> int:
    """Remove cloud copies whose time is up (Basic plan keeps them 2 days). Safe to call often."""
    from datetime import datetime, timezone
    from pathlib import Path
    from sqlalchemy import select
    from app.models import RoomRecording
    rows = (await db.execute(select(RoomRecording).where(RoomRecording.expires_at.is_not(None), RoomRecording.expires_at < datetime.now(timezone.utc)))).scalars().all()
    for r in rows:
        if r.storage == "r2" and r.object_key: await asyncio.to_thread(delete_object, r.object_key)
        elif r.path:
            try: Path(r.path).unlink(missing_ok=True)
            except OSError: pass
        await db.delete(r)
    if rows: await db.commit()
    return len(rows)
