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


_POOL = None


def _pool():
    """Conversions run in separate worker processes, so several files (and the pages of one big PDF) are converted at the same time on different CPU cores."""
    global _POOL
    if _POOL is None:
        import multiprocessing, os
        from concurrent.futures import ProcessPoolExecutor
        n = int(os.environ.get("DOCCONVERT_WORKERS") or max(2, min(4, (os.cpu_count() or 2))))
        _POOL = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("spawn"))
    return _POOL


@router.on_event("startup")
async def _warm_workers():
    """Start the conversion workers when the app starts, so the first conversion is not slowed by loading the libraries."""
    try:
        pool = _pool(); loop = asyncio.get_running_loop()
        for _ in range(pool._max_workers): loop.run_in_executor(pool, dc.warm)
    except Exception: log.warning("Conversion workers could not be started early")


async def _go(fn, *args):
    """Run fn(*args) in the worker pool; if the pool is unavailable, run it in a thread so the conversion still happens."""
    global _POOL
    loop = asyncio.get_running_loop()
    try: return await loop.run_in_executor(_pool(), fn, *args)
    except (OSError, RuntimeError) as exc:
        if exc.__class__.__name__ in ("BrokenProcessPool", "PermissionError", "OSError", "RuntimeError"):
            log.warning("Worker pool unavailable (%s); converting in a thread", exc.__class__.__name__)
            try: _POOL = None
            except Exception: pass
            return await asyncio.to_thread(fn, *args)
        raise


@router.post("/convert")
async def convert(payload: dict, user: User = Depends(principal)):
    """{kind: wp|sheet|deck, to: pdf|docx|xlsx|pptx, title, content, shown?, shapes?} -> {filename, mime, data (base64)}"""
    kind, to = str(payload.get("kind") or ""), str(payload.get("to") or "")
    if (kind, to) not in ROUTES: raise HTTPException(422, "That conversion is not available.")
    content = payload.get("content")
    if not isinstance(content, str): raise HTTPException(422, "Nothing to convert.")
    title = str(payload.get("title") or "")[:200]
    try: data = await _go(dc.run_convert, kind, to, content, title, payload.get("shown"), payload.get("shapes") if isinstance(payload.get("shapes"), dict) else {})
    except dc.ConvertError as exc: raise HTTPException(422, str(exc))
    except Exception:
        log.exception("Conversion failed (%s to %s)", kind, to)
        raise HTTPException(500, "The file could not be converted. Try again, or tell the administrator if it keeps happening.")
    return {"filename": _name(title, to), "mime": MIME[to], "data": base64.b64encode(data).decode()}


async def _pdf_wp(raw: bytes, exact: bool) -> dict:
    """A PDF as a WordPerfect document. A long PDF in exact mode is split into page groups that are converted at the same time."""
    if not exact: return await _go(dc.pdf_to_wp, raw, False)
    n = await _go(dc.pdf_page_count, raw)
    if n <= 4: return await _go(dc.pdf_to_wp_exact, raw, None)
    workers = max(2, min(4, __import__("os").cpu_count() or 2)); size = max(2, -(-n // workers))
    parts = await asyncio.gather(*[_go(dc.pdf_to_wp_exact, raw, list(range(i, min(n, i + size)))) for i in range(0, n, size)])
    notes = list(dict.fromkeys(x for p in parts for x in p["notes"]))
    return {"html": "".join(p["html"] for p in parts), "pages": n, "notes": notes}


@router.post("/pdf-to-wp")
async def pdf_to_wp(payload: dict, user: User = Depends(principal)):
    """{name, data (base64 PDF)} -> {html, pages, notes}: the PDF rebuilt as a WordPerfect document."""
    try: raw = base64.b64decode(str(payload.get("data") or ""), validate=False)
    except Exception: raise HTTPException(422, "The file could not be read.")
    try: res = await _pdf_wp(raw, str(payload.get("mode") or "exact") != "flow")
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
        if ext == "docx": r = await _go(dc.docx_to_wp, raw); return {"kind": "wp", "title": title, "content": r["html"], "notes": r["notes"]}
        if ext == "xlsx": r = await _go(dc.xlsx_to_book, raw); return {"kind": "sheet", "title": title, "content": r["content"], "notes": r["notes"]}
        r = await _go(dc.pptx_to_deck, raw); return {"kind": "deck", "title": title, "content": r["content"], "notes": r["notes"]}
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
        if fn: pdf = await _go(fn, raw, base)
        elif ext in ("html", "htm", "txt", "md"):
            t = raw.decode("utf-8", "replace")
            html = t if ext in ("html", "htm") else "".join(f"<p>{dc.esc(l) if l else '<br>'}</p>" for l in t.splitlines())
            pdf = await _go(dc.wp_to_pdf, html, base)
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
        res = await _pdf_wp(raw, str(payload.get("mode") or "exact") != "flow")
        docx = await _go(dc.wp_to_docx, res["html"], base)
    except dc.ConvertError as e: raise HTTPException(422, str(e))
    return {"filename": f"{base}.docx", "mime": MIME["docx"], "data": base64.b64encode(docx).decode(), "notes": res["notes"]}
