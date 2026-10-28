"""Doc Converter: turn WordPerfect, SpreadTable and PowerPresentation files into PDF, Word, Excel or PowerPoint, and a PDF into a WordPerfect document."""
import asyncio, base64, logging
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import principal
from app.models import User
from app.services import docconvert as dc

log = logging.getLogger("isift.docconvert")
router = APIRouter(prefix="/api/v1/docs", tags=["doc-converter"])

MIME = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
ROUTES = {("wp", "pdf"), ("wp", "docx"), ("sheet", "pdf"), ("sheet", "xlsx"), ("deck", "pdf"), ("deck", "pptx")}


def _name(title: str, ext: str) -> str:
    base = "".join(c for c in (title or "file") if c.isalnum() or c in " -_").strip()[:80] or "file"
    return f"{base}.{ext}"


def _run(kind: str, to: str, content: str, title: str, shown, shapes) -> bytes:
    if (kind, to) == ("wp", "pdf"): return dc.wp_to_pdf(content, title)
    if (kind, to) == ("wp", "docx"): return dc.wp_to_docx(content, title)
    if (kind, to) == ("sheet", "pdf"): return dc.sheet_to_pdf(content, shown, title)
    if (kind, to) == ("sheet", "xlsx"): return dc.sheet_to_xlsx(content, title)
    if (kind, to) == ("deck", "pdf"): return dc.deck_to_pdf(content, shapes, title)
    return dc.deck_to_pptx(content, shapes, title)


@router.post("/convert")
async def convert(payload: dict, user: User = Depends(principal)):
    """{kind: wp|sheet|deck, to: pdf|docx|xlsx|pptx, title, content, shown?, shapes?} -> {filename, mime, data (base64)}"""
    kind, to = str(payload.get("kind") or ""), str(payload.get("to") or "")
    if (kind, to) not in ROUTES: raise HTTPException(422, "That conversion is not available.")
    content = payload.get("content")
    if not isinstance(content, str): raise HTTPException(422, "Nothing to convert.")
    title = str(payload.get("title") or "")[:200]
    try: data = await asyncio.to_thread(_run, kind, to, content, title, payload.get("shown"), payload.get("shapes") if isinstance(payload.get("shapes"), dict) else {})
    except dc.ConvertError as exc: raise HTTPException(422, str(exc))
    except Exception:
        log.exception("Conversion failed (%s to %s)", kind, to)
        raise HTTPException(500, "The file could not be converted. Try again, or tell the administrator if it keeps happening.")
    return {"filename": _name(title, to), "mime": MIME[to], "data": base64.b64encode(data).decode()}


@router.post("/pdf-to-wp")
async def pdf_to_wp(payload: dict, user: User = Depends(principal)):
    """{name, data (base64 PDF)} -> {html, pages, notes}: the PDF rebuilt as a WordPerfect document."""
    try: raw = base64.b64decode(str(payload.get("data") or ""), validate=False)
    except Exception: raise HTTPException(422, "The file could not be read.")
    try: res = await asyncio.to_thread(dc.pdf_to_wp, raw)
    except dc.ConvertError as exc: raise HTTPException(422, str(exc))
    except Exception:
        log.exception("PDF to WordPerfect failed")
        raise HTTPException(500, "The PDF could not be converted. It may be damaged or protected.")
    return res
