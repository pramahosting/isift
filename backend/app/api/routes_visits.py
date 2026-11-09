"""Counting visits that come from tagged links, and showing the admin which link brought visits and sign-ups."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal, require_admin
from app.models import User
from app.services import visits as vs

router = APIRouter(prefix="/api/v1", tags=["traffic"])


class Tag(BaseModel):
    source: str = ""; medium: str = ""; campaign: str = ""; content: str = ""; vid: str = ""


@router.post("/track/visit")
async def track_visit(b: Tag, db: AsyncSession = Depends(get_db)):
    try: await vs.record_visit(db, source=b.source, medium=b.medium, campaign=b.campaign, content=b.content, vid=b.vid)
    except Exception: pass                                      # counting must never get in anyone's way
    return {"ok": True}


@router.post("/track/attribute")
async def track_attribute(b: Tag, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    try: await vs.attribute(db, user.email, source=b.source, medium=b.medium, campaign=b.campaign, content=b.content)
    except Exception: pass
    return {"ok": True}


def _d(v):
    try: return datetime.fromisoformat(v)
    except Exception: return None


@router.get("/admin/traffic")
async def traffic(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    items = await vs.log(db); attr = await vs.attribution(db)
    now = datetime.now(timezone.utc)
    users = {(u.email or "").lower(): u for u in (await db.execute(select(User))).scalars().all()}
    rows: dict[tuple, dict] = {}
    def row(src, med, cont):
        return rows.setdefault((src, med, cont), {"source": src, "medium": med, "content": cont, "visits": 0, "visits_7d": 0, "last_visit": None, "signups": 0, "people": []})
    for i in items:
        r = row(i.get("source", ""), i.get("medium", ""), i.get("content", "")); r["visits"] += 1
        t = _d(i.get("at"))
        if t and t >= now - timedelta(days=7): r["visits_7d"] += 1
        if t and (not r["last_visit"] or t.isoformat() > r["last_visit"]): r["last_visit"] = t.isoformat()
    for email, a in attr.items():
        r = row(a.get("source", ""), a.get("medium", ""), a.get("content", ""))
        r["signups"] += 1; r["people"].append(email)
    out = sorted(rows.values(), key=lambda r: (-r["visits"], -r["signups"]))
    for r in out: r["rate"] = round(100 * r["signups"] / r["visits"], 1) if r["visits"] else None
    return {"rows": out, "total_visits": len(items), "total_signups": len(attr), "since": items[0]["at"] if items else None}
