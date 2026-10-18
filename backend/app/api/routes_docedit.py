"""Edit a PDF or Word file (add text, delete text, sign with a drawn signature) and keep drawn signatures for later.
Nothing about the uploaded file is stored: it comes in with each request and the edited copy goes straight back."""
import asyncio, base64
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.models import User, SavedSignature
from app.services import docedit as de

router = APIRouter(prefix="/api/v1/docedit", tags=["docedit"])

async def _run(fn, *a):
    try: return await asyncio.to_thread(fn, *a)
    except de.EditError as e: raise HTTPException(400, str(e))

@router.post("/inspect")
async def inspect(payload: dict, user: User = Depends(principal)):
    try: raw = de.b64_in(payload.get("data")); kind = de.kind_of(payload.get("name"), raw)
    except de.EditError as e: raise HTTPException(400, str(e))
    out = {**(await _run(de.pdf_inspect if kind == "pdf" else de.docx_inspect, raw)), "name": payload.get("name")}
    if kind == "pdf": out["signatures"] = await asyncio.to_thread(de.pdf_signatures, raw)
    return out

@router.post("/apply")
async def apply(payload: dict, user: User = Depends(principal)):
    try: raw = de.b64_in(payload.get("data")); kind = de.kind_of(payload.get("name"), raw)
    except de.EditError as e: raise HTTPException(400, str(e))
    ops = payload.get("ops")
    if not isinstance(ops, list) or not ops or len(ops) > de.MAX_OPS or not all(isinstance(o, dict) for o in ops): raise HTTPException(400, "There are no changes to apply.")
    if kind == "pdf" and await asyncio.to_thread(de.pdf_signatures, raw):
        raise HTTPException(400, "This PDF is digitally signed, so editing it would break the signature. Use Revert changes to go back to the unsigned file.")
    out = await _run(de.pdf_apply if kind == "pdf" else de.docx_apply, raw, ops)
    out, warnings = out if kind == "pdf" else (out, [])
    return {"name": payload.get("name"), "data": base64.b64encode(out).decode(), "warnings": warnings}

@router.post("/certificate")
async def create_certificate(payload: dict, user: User = Depends(principal)):
    """Make a self-signed certificate file for the person to keep. It is never stored here."""
    p12 = await _run(de.make_certificate, str(payload.get("name") or user.display_name or ""), str(payload.get("email") or ""), str(payload.get("password") or ""))
    return {"name": "isift-signing-certificate.p12", "data": base64.b64encode(p12).decode()}

@router.post("/certify")
async def certify(payload: dict, user: User = Depends(principal)):
    """Add a certified digital signature to a PDF using the person's own certificate. The certificate and password are used once and not kept."""
    try: raw = de.b64_in(payload.get("data")); kind = de.kind_of(payload.get("name"), raw); p12 = de.b64_in(payload.get("p12"), 200_000)
    except de.EditError as e: raise HTTPException(400, str(e))
    if kind != "pdf": raise HTTPException(400, "Certified digital signatures can be added to PDF files. Download your Word file, save it as a PDF, then sign that.")
    if await asyncio.to_thread(de.pdf_signatures, raw): raise HTTPException(400, "This PDF already has a digital signature. Revert to the unsigned file to sign it again.")
    out = await _run(de.pdf_certify, raw, p12, str(payload.get("password") or ""), str(payload.get("reason") or ""), str(payload.get("location") or ""), str(payload.get("contact") or ""),
                     bool(payload.get("visible", True)), int(payload.get("page") or 0), bool(payload.get("lock", True)))
    return {"name": payload.get("name"), "data": base64.b64encode(out).decode(), "signatures": await asyncio.to_thread(de.pdf_signatures, out)}

def _sig(s: SavedSignature): return {"id": s.id, "name": s.name, "png": s.png}

@router.get("/signatures")
async def signatures(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SavedSignature).where(SavedSignature.user_id == user.id).order_by(SavedSignature.created_at))).scalars().all()
    return {"items": [_sig(s) for s in rows]}

@router.post("/signatures")
async def save_signature(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    try: raw = de.png_ok(de.b64_in(payload.get("png"), 400_000))
    except de.EditError as e: raise HTTPException(400, str(e))
    if (await db.execute(select(func.count()).select_from(SavedSignature).where(SavedSignature.user_id == user.id))).scalar() >= 10:
        raise HTTPException(400, "You can keep up to 10 signatures. Delete one first.")
    s = SavedSignature(user_id=user.id, name=(str(payload.get("name") or "My signature").strip() or "My signature")[:80], png=base64.b64encode(raw).decode())
    s.png = "data:image/png;base64," + s.png; db.add(s); await db.commit(); return _sig(s)

@router.delete("/signatures/{sid}")
async def delete_signature(sid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    s = await db.get(SavedSignature, sid)
    if not s or s.user_id != user.id: raise HTTPException(404, "Not found")
    await db.delete(s); await db.commit(); return {"ok": True}
