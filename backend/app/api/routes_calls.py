"""Calls between iSift users, like a phone call inside the app: ring a signed-in person, they accept or decline, and both land in a private two-person room.
Ringing travels over one small websocket per signed-in browser tab (/ws/calls). Nothing about a call is stored except the meeting room it opens."""
import asyncio, json, time, uuid
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.models import User
from app.services import entitlements as ent

router = APIRouter(prefix="/api/v1", tags=["calls"])
ONLINE: dict[str, set] = {}          # user id -> open websockets (a person may have several tabs or devices)
RINGING: dict[str, dict] = {}        # call id -> who is calling whom
RING_SECONDS = 45

async def _tell(user_id: str, msg: dict) -> int:
    n = 0
    for ws in list(ONLINE.get(user_id, ())):
        try: await ws.send_text(json.dumps(msg)); n += 1
        except Exception: ONLINE.get(user_id, set()).discard(ws)
    return n

def _who(u: User) -> dict: return {"name": u.display_name or u.email, "email": u.email}

@router.websocket("/ws/calls")
async def calls_socket(ws: WebSocket):
    await ws.accept(); me = None
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=20))
        from app.api.routes_rooms import _user_from_token
        me = await _user_from_token(first.get("token")) if first.get("type") == "auth" else None
        if not me: await ws.close(); return
        ONLINE.setdefault(me.id, set()).add(ws); await ws.send_text(json.dumps({"type": "ready"}))
        while True: await ws.receive_text()                      # keep-alive pings from the page
    except (WebSocketDisconnect, asyncio.TimeoutError, json.JSONDecodeError, RuntimeError): pass
    finally:
        if me and me.id in ONLINE:
            ONLINE[me.id].discard(ws)
            if not ONLINE[me.id]: ONLINE.pop(me.id, None)

async def _ring_timeout(call_id: str):
    await asyncio.sleep(RING_SECONDS)
    c = RINGING.pop(call_id, None)
    if c:
        await _tell(c["to"], {"type": "ended", "call_id": call_id, "reason": "missed"})
        await _tell(c["from"], {"type": "missed", "call_id": call_id})

@router.post("/calls")
async def place_call(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await ent.need_calls(user, db)
    email = str(payload.get("to") or "").strip().lower()
    callee = (await db.execute(select(User).where(func.lower(User.email) == email, User.is_active.isnot(False)))).scalars().first() if email else None
    if not callee: raise HTTPException(404, "No iSift user has that email address. Calls go to people with an iSift account.")
    if callee.id == user.id: raise HTTPException(400, "You cannot call yourself.")
    if callee.id not in ONLINE: raise HTTPException(409, f"{callee.display_name or callee.email} is not online in iSift right now. Send an invitation link instead, or try again later.")
    from app.api.routes_rooms import make_room
    room, _m = await make_room(db, user, f"Call with {callee.display_name or callee.email}", str(payload.get("base_url") or ""), access="signed_in", waiting_room=False, options={"mute_on_entry": False})
    call_id = uuid.uuid4().hex[:12]; RINGING[call_id] = {"from": user.id, "to": callee.id, "code": room.code, "at": time.time()}
    await _tell(callee.id, {"type": "incoming", "call_id": call_id, "code": room.code, "from": _who(user), "seconds": RING_SECONDS})
    asyncio.create_task(_ring_timeout(call_id))
    await ent.bump(db, user.email, "calls", 1)
    return {"call_id": call_id, "code": room.code, "to": _who(callee)}

@router.post("/calls/{call_id}/answer")
async def answer_call(call_id: str, payload: dict, user: User = Depends(principal)):
    c = RINGING.get(call_id)
    if not c or c["to"] != user.id: raise HTTPException(404, "This call has ended.")
    RINGING.pop(call_id, None)
    accept = bool((payload or {}).get("accept"))
    await _tell(c["from"], {"type": "accepted" if accept else "declined", "call_id": call_id, "code": c["code"], "by": _who(user)})
    await _tell(c["to"], {"type": "ended", "call_id": call_id, "reason": "answered" if accept else "declined"})    # other tabs of the same person stop ringing
    return {"ok": True, "code": c["code"] if accept else None}

@router.post("/calls/{call_id}/cancel")
async def cancel_call(call_id: str, user: User = Depends(principal)):
    c = RINGING.get(call_id)
    if not c or c["from"] != user.id: raise HTTPException(404, "This call has ended.")
    RINGING.pop(call_id, None)
    await _tell(c["to"], {"type": "ended", "call_id": call_id, "reason": "cancelled"})
    return {"ok": True}
