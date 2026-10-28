"""Doc Converter: turn WordPerfect, SpreadTable and PowerPresentation files into PDF, Word, Excel or PowerPoint, and a PDF into a WordPerfect document."""
import asyncio, base64, logging, re
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
    try: res = await asyncio.to_thread(dc.pdf_to_wp, raw, str(payload.get("mode") or "exact") != "flow")
    except dc.ConvertError as exc: raise HTTPException(422, str(exc))
    except Exception:
        log.exception("PDF to WordPerfect failed")
        raise HTTPException(500, "The PDF could not be converted. It may be damaged or protected.")
    return res


@router.post("/import")
async def import_office(payload: dict, user: User = Depends(principal)):
    """{name, data (base64 .docx / .xlsx / .pptx)} -> {kind, title, content, notes}: a Microsoft file as an editable WordPerfect, SpreadTable or PowerPresentation file."""
    name = str(payload.get("name") or "")
    try: raw = base64.b64decode(str(payload.get("data") or "").split(",", 1)[-1], validate=False)
    except Exception: raise HTTPException(422, "The file could not be read.")
    if not raw: raise HTTPException(422, "The file is empty.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ("docx", "xlsx", "pptx"): raise HTTPException(422, "Choose a Word (.docx), Excel (.xlsx) or PowerPoint (.pptx) file.")
    if raw[:2] != b"PK": raise HTTPException(422, f"That is not a real .{ext} file. Older .doc, .xls and .ppt files must be saved in the newer format first.")
    title = re.sub(r"\.[A-Za-z0-9]+$", "", name)[:200] or "Imported"
    try:
        if ext == "docx": r = await asyncio.to_thread(dc.docx_to_wp, raw); return {"kind": "wp", "title": title, "content": r["html"], "notes": r["notes"]}
        if ext == "xlsx": r = await asyncio.to_thread(dc.xlsx_to_book, raw); return {"kind": "sheet", "title": title, "content": r["content"], "notes": r["notes"]}
        r = await asyncio.to_thread(dc.pptx_to_deck, raw); return {"kind": "deck", "title": title, "content": r["content"], "notes": r["notes"]}
    except dc.ConvertError as e: raise HTTPException(422, str(e))


@router.post("/file-to-pdf")
async def file_to_pdf(payload: dict, user: User = Depends(principal)):
    """{name, data (base64 .docx / .pptx / .xlsx / .html / .txt)} -> {filename, mime, data}: a file from the person's computer as a PDF. Nothing is saved in iSift."""
    name = str(payload.get("name") or "")
    try: raw = base64.b64decode(str(payload.get("data") or "").split(",", 1)[-1], validate=False)
    except Exception: raise HTTPException(422, "The file could not be read.")
    if not raw: raise HTTPException(422, "The file is empty.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    base = re.sub(r"\.[A-Za-z0-9]+$", "", name)[:120] or "converted"
    if ext in ("docx", "pptx", "xlsx") and raw[:2] != b"PK": raise HTTPException(422, f"That is not a real .{ext} file. Older .doc, .xls and .ppt files must be saved in the newer format first.")
    fn = {"docx": dc.docx_to_pdf, "pptx": dc.pptx_to_pdf, "xlsx": dc.xlsx_to_pdf}.get(ext)
    try:
        if fn: pdf = await asyncio.to_thread(fn, raw, base)
        elif ext in ("html", "htm", "txt", "md"):
            t = raw.decode("utf-8", "replace")
            html = t if ext in ("html", "htm") else "".join(f"<p>{dc.esc(l) if l else '<br>'}</p>" for l in t.splitlines())
            pdf = await asyncio.to_thread(dc.wp_to_pdf, html, base)
        else: raise HTTPException(422, "Choose a Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML or text file.")
    except dc.ConvertError as e: raise HTTPException(422, str(e))
    return {"filename": f"{base}.pdf", "mime": "application/pdf", "data": base64.b64encode(pdf).decode()}


@router.post("/pdf-to-docx")
async def pdf_to_docx(payload: dict, user: User = Depends(principal)):
    """{name, data (base64 PDF), mode?} -> {filename, mime, data}: a PDF as a Word file, straight away. mode "flow" gives reflowing text instead of exact pages."""
    name = str(payload.get("name") or "")
    try: raw = base64.b64decode(str(payload.get("data") or "").split(",", 1)[-1], validate=False)
    except Exception: raise HTTPException(422, "The file could not be read.")
    base = re.sub(r"\.[A-Za-z0-9]+$", "", name)[:120] or "converted"
    try:
        res = await asyncio.to_thread(dc.pdf_to_wp, raw, str(payload.get("mode") or "exact") != "flow")
        docx = await asyncio.to_thread(dc.wp_to_docx, res["html"], base)
    except dc.ConvertError as e: raise HTTPException(422, str(e))
    return {"filename": f"{base}.docx", "mime": MIME["docx"], "data": base64.b64encode(docx).decode(), "notes": res["notes"]}
