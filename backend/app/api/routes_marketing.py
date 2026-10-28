"""Sales & Marketing files (videos, the playbook, anything else) kept by the administrator.
Admin: list, upload, replace, edit, delete. Public: the landing-page video and any file marked public."""
import asyncio, mimetypes, re, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_admin
from app.models import User, MarketingAsset, AuditLog

router = APIRouter(prefix="/api/v1", tags=["marketing"])
DB_LIMIT = 150 * 1024 * 1024
R2_LIMIT = 2 * 1024 * 1024 * 1024

def _now(): return datetime.now(timezone.utc)

def _kind(name: str, mime: str) -> str:
    if mime.startswith("video/"): return "video"
    if mime == "application/pdf" or name.lower().endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md", ".csv")): return "document"
    return "other"

def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name or "file").name)[:200] or "file"

def _row(a: MarketingAsset) -> dict:
    return {"id": a.id, "kind": a.kind, "title": a.title, "description": a.description, "filename": a.filename, "mimetype": a.mimetype, "size_bytes": a.size_bytes,
            "storage": a.storage, "public": a.public, "landing": a.landing, "created_at": a.created_at, "updated_at": a.updated_at}

async def _receive(request: Request) -> tuple[Path, int]:
    """The browser sends the file itself as the request body; it is written to disk as it arrives."""
    tmp = Path(tempfile.mkdtemp(prefix="mkt_")) / "up.bin"; n = 0
    with tmp.open("wb") as f:
        async for chunk in request.stream():
            n += len(chunk)
            if n > R2_LIMIT: f.close(); tmp.unlink(missing_ok=True); raise HTTPException(413, "That file is larger than 2 GB.")
            f.write(chunk)
    if n == 0: tmp.unlink(missing_ok=True); raise HTTPException(400, "The file was empty.")
    return tmp, n

async def _place(a: MarketingAsset, path: Path, size: int):
    """Keep the file in Cloudflare R2 when it is set up in Admin Console, otherwise in the database."""
    from app.services import storage
    old_key = a.object_key if a.storage == "r2" else None
    try:
        if storage.configured():
            key = f"{storage.top_folder()}/marketing/{a.id}-{uuid.uuid4().hex[:6]}-{_safe(a.filename)}"
            await asyncio.to_thread(storage._put, path, key, a.mimetype)
            a.storage, a.object_key, a.data = "r2", key, None
        else:
            if size > DB_LIMIT: raise HTTPException(413, "Files over 150 MB need Cloudflare R2 storage. Set it up in Admin Console, API Keys, then upload again.")
            a.storage, a.object_key, a.data = "database", None, path.read_bytes()
    finally:
        path.unlink(missing_ok=True)
        try: path.parent.rmdir()
        except OSError: pass
    a.size_bytes = size
    if old_key and old_key != a.object_key: await asyncio.to_thread(storage.delete_object, old_key)

async def _get(db: AsyncSession, aid: str) -> MarketingAsset:
    a = await db.get(MarketingAsset, aid)
    if not a: raise HTTPException(404, "File not found.")
    return a

@router.get("/admin/marketing")
async def list_assets(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(MarketingAsset).order_by(MarketingAsset.created_at.desc()))).scalars().all()
    from app.services import storage
    return {"items": [_row(a) for a in rows], "r2": storage.configured()}

@router.post("/admin/marketing")
async def upload_asset(request: Request, filename: str, title: str = "", description: str = "", user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    name = _safe(filename); mime = request.headers.get("content-type", "")
    if not mime or mime == "application/octet-stream": mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    path, n = await _receive(request)
    a = MarketingAsset(kind=_kind(name, mime), title=(title.strip() or Path(name).stem)[:200], description=description.strip()[:2000], filename=name, mimetype=mime[:120])
    await _place(a, path, n)
    db.add(a); db.add(AuditLog(actor=user.email, action="marketing.upload", resource_type="marketing", safe_metadata={"file": name, "bytes": n})); await db.commit()
    return _row(a)

@router.put("/admin/marketing/{aid}/file")
async def replace_file(aid: str, request: Request, filename: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get(db, aid); name = _safe(filename); mime = request.headers.get("content-type", "")
    if not mime or mime == "application/octet-stream": mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    path, n = await _receive(request)
    a.filename, a.mimetype, a.kind, a.updated_at = name, mime[:120], _kind(name, mime), _now()
    await _place(a, path, n)
    if a.kind != "video": a.landing = False
    db.add(AuditLog(actor=user.email, action="marketing.replace", resource_type="marketing", resource_id=a.id, safe_metadata={"file": name})); await db.commit()
    return _row(a)

class Patch(BaseModel):
    title: str | None = None
    description: str | None = None
    public: bool | None = None
    landing: bool | None = None

@router.patch("/admin/marketing/{aid}")
async def edit_asset(aid: str, body: Patch, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get(db, aid)
    if body.title is not None: a.title = body.title.strip()[:200] or a.title
    if body.description is not None: a.description = body.description.strip()[:2000]
    if body.public is not None:
        a.public = body.public
        if not a.public: a.landing = False
    if body.landing is not None:
        if body.landing:
            if a.kind != "video": raise HTTPException(400, "Only a video can be shown behind the Watch button.")
            await db.execute(update(MarketingAsset).where(MarketingAsset.id != a.id).values(landing=False))
            a.landing, a.public = True, True
        else: a.landing = False
    a.updated_at = _now(); await db.commit()
    return _row(a)

@router.delete("/admin/marketing/{aid}")
async def delete_asset(aid: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = await _get(db, aid)
    if a.storage == "r2" and a.object_key:
        from app.services import storage
        await asyncio.to_thread(storage.delete_object, a.object_key)
    await db.delete(a); db.add(AuditLog(actor=user.email, action="marketing.delete", resource_type="marketing", resource_id=aid, safe_metadata={"file": a.filename})); await db.commit()
    return {"ok": True}

async def _serve(db: AsyncSession, a: MarketingAsset, request: Request, download: bool):
    disp = f'{"attachment" if download else "inline"}; filename="{a.filename.replace(chr(34), "")}"'
    if a.storage == "r2" and a.object_key:
        from app.services import storage
        try:
            url = storage.client().generate_presigned_url("get_object", Params={"Bucket": settings.r2_bucket, "Key": a.object_key, "ResponseContentType": a.mimetype, "ResponseContentDisposition": disp}, ExpiresIn=3600)
        except Exception: raise HTTPException(502, "Cloud storage could not be reached.")
        return RedirectResponse(url, status_code=307)
    blob = (await db.execute(select(MarketingAsset.data).where(MarketingAsset.id == a.id))).scalar_one_or_none()
    if blob is None: raise HTTPException(410, "This file is no longer stored.")
    blob = bytes(blob); total = len(blob); hdr = {"Content-Disposition": disp, "Accept-Ranges": "bytes", "Cache-Control": "private, max-age=300"}
    m = re.match(r"bytes=(\d*)-(\d*)$", request.headers.get("range", "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1): s = int(m.group(1)); e = int(m.group(2)) if m.group(2) else total - 1
        else: s = max(0, total - int(m.group(2))); e = total - 1
        e = min(e, total - 1)
        if s > e or s >= total: return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        return Response(blob[s:e + 1], status_code=206, media_type=a.mimetype, headers={**hdr, "Content-Range": f"bytes {s}-{e}/{total}"})
    return Response(blob, media_type=a.mimetype, headers=hdr)

@router.get("/admin/marketing/{aid}/file")
async def admin_file(aid: str, request: Request, download: bool = False, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await _serve(db, await _get(db, aid), request, download)

@router.get("/marketing/landing")
async def landing_video(db: AsyncSession = Depends(get_db)):
    a = (await db.execute(select(MarketingAsset).where(MarketingAsset.landing == True, MarketingAsset.public == True, MarketingAsset.kind == "video").limit(1))).scalar_one_or_none()  # noqa: E712
    return {"video": {"id": a.id, "title": a.title, "mimetype": a.mimetype, "v": int(a.updated_at.timestamp()) if a.updated_at else 0} if a else None}

@router.get("/marketing/{aid}/file")
async def public_file(aid: str, request: Request, download: bool = False, db: AsyncSession = Depends(get_db)):
    a = await db.get(MarketingAsset, aid)
    if not a or not a.public: raise HTTPException(404, "File not found.")
    return await _serve(db, a, request, download)
