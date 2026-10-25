"""The Administration manual: a PDF only a signed-in administrator can open (it is not on the public website)."""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.core.security import require_admin
from app.models import User

router = APIRouter(prefix="/api/v1/admin", tags=["manuals"])
_FILE = Path(__file__).resolve().parents[1] / "private_manuals" / "administration.pdf"

@router.get("/manual")
async def administration_manual(user: User = Depends(require_admin)):
    if not _FILE.exists(): raise HTTPException(404, "The Administration manual is not installed.")
    return FileResponse(_FILE, media_type="application/pdf", filename="iSift-administration-manual.pdf", headers={"Cache-Control": "private, no-store"})
