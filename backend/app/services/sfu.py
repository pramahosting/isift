"""Cloudflare Realtime SFU: carries video for big meetings so each person uploads once.

The browser never sees the application secret. It sends its WebRTC offers and answers to this server over the meeting's
WebSocket, and this server passes them on to Cloudflare's HTTPS API."""
import logging
import httpx
from app.core.config import settings

log = logging.getLogger("isift")
BASE = "https://rtc.live.cloudflare.com/v1"


class SfuError(Exception):
    pass


def configured() -> bool:
    return bool(settings.cf_sfu_app_id and settings.cf_sfu_app_secret)


async def _call(method: str, path: str, body: dict | None = None) -> dict:
    if not configured(): raise SfuError("The video server for big meetings is not set up.")
    url = f"{BASE}/apps/{settings.cf_sfu_app_id}{path}"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.request(method, url, headers={"Authorization": f"Bearer {settings.cf_sfu_app_secret}"}, json=body)
    except Exception as ex:
        log.exception("Cloudflare SFU request failed")
        raise SfuError("Could not reach the video server. Try again in a moment.") from ex
    try: j = r.json()
    except Exception: j = {}
    if r.status_code >= 400 or j.get("errorCode"):
        log.warning("Cloudflare SFU said %s %s %s", r.status_code, j.get("errorCode"), j.get("errorDescription"))
        raise SfuError(j.get("errorDescription") or f"The video server refused the request ({r.status_code}).")
    return j


async def new_session() -> str:
    j = await _call("POST", "/sessions/new")
    sid = j.get("sessionId")
    if not sid: raise SfuError("The video server did not start a session.")
    return sid


async def push(session: str, offer_sdp: str, tracks: list[dict]) -> dict:
    """Publish local tracks: send the browser's offer, get the answer to hand back."""
    j = await _call("POST", f"/sessions/{session}/tracks/new", {"sessionDescription": {"type": "offer", "sdp": offer_sdp},
                    "tracks": [{"location": "local", "mid": t["mid"], "trackName": t["name"]} for t in tracks]})
    for t in j.get("tracks") or []:
        if t.get("errorCode"): raise SfuError(t.get("errorDescription") or "The video server could not take one of your tracks.")
    return j


async def pull(session: str, wanted: list[dict]) -> dict:
    """Subscribe to other people's tracks: Cloudflare answers with an offer for the browser to accept."""
    j = await _call("POST", f"/sessions/{session}/tracks/new", {"tracks": [{"location": "remote", "sessionId": t["session"], "trackName": t["name"]} for t in wanted]})
    return j


async def renegotiate(session: str, answer_sdp: str) -> None:
    await _call("PUT", f"/sessions/{session}/renegotiate", {"sessionDescription": {"type": "answer", "sdp": answer_sdp}})
