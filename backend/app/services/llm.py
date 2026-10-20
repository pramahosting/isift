"""Groq client for minutes, action items, briefings and speech-to-text.

Groq speaks the OpenAI wire format, so this uses plain HTTPS and adds no dependency. The chat model is
always the one saved in Admin Console (Groq model). Structured output is requested as JSON and checked
with pydantic; the schema is put in the prompt because not every Groq model supports server-side schemas.
"""
import asyncio, json, logging, re
import httpx
from pydantic import BaseModel, ValidationError
from app.core.config import settings

log = logging.getLogger("isift")
BASE = "https://api.groq.com/openai/v1"
DEFAULT_CHAT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_STT_MODEL = "whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 24 * 1024 * 1024  # Groq accepts 25 MB per file on the free tier

class AIUnavailable(RuntimeError): pass

def _key() -> str:
    k = (settings.groq_api_key or "").strip().strip("\"'")
    return k[7:].strip() if k.lower().startswith("bearer ") else k

def chat_model() -> str: return (settings.groq_model or "").strip() or DEFAULT_CHAT_MODEL
def stt_model() -> str: return (settings.groq_transcription_model or "").strip() or DEFAULT_STT_MODEL

def ai_configured() -> bool: return bool(_key())
def transcription_configured() -> bool: return bool(_key())

def auth_headers() -> dict: return {"Authorization": f"Bearer {_key()}"}

def _safe_error(resp: httpx.Response) -> str:
    try: msg = (resp.json().get("error") or {}).get("message") or ""
    except Exception: msg = ""
    msg = re.sub(r"\s+", " ", msg).strip()[:160]
    return f"Groq request failed ({resp.status_code}{': ' + msg if msg else ''})"

async def chat_json(messages: list[dict], model: type[BaseModel], timeout: int = 60, retries: int = 2) -> BaseModel:
    """Call the Groq chat model and return a validated pydantic object."""
    if not ai_configured(): raise AIUnavailable("Groq is not set up. The administrator can add a Groq key under Admin Console.")
    schema = model.model_json_schema()
    msgs = [*messages, {"role": "system", "content": "Respond only with one JSON object that matches this JSON schema. No other text. " + json.dumps(schema)}]
    body = {"model": chat_model(), "messages": msgs, "response_format": {"type": "json_object"}, "temperature": 0}
    last = "Groq request failed"
    for attempt in range(retries + 2):
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.post(f"{BASE}/chat/completions", headers={**auth_headers(), "Content-Type": "application/json"}, json=body)
        if resp.status_code in (429, 500, 502, 503, 504):
            last = _safe_error(resp); await asyncio.sleep(min(2 ** attempt, 8)); continue
        if resp.status_code >= 400: raise AIUnavailable(_safe_error(resp))
        choice = (resp.json().get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        if not content: last = "Groq returned no content" + (f" ({choice.get('finish_reason')})" if choice.get("finish_reason") else ""); continue
        try: return model.model_validate_json(content)
        except ValidationError: last = "Groq returned JSON that did not match the expected format"; continue
    raise AIUnavailable(last)

def to_messages(prompt, variables: dict) -> list[dict]:
    """Render a langchain ChatPromptTemplate into chat-completion messages."""
    role = {"system": "system", "human": "user", "ai": "assistant"}
    return [{"role": role.get(m.type, "user"), "content": m.content} for m in prompt.format_messages(**variables)]

async def transcribe(filename: str, data: bytes) -> dict:
    """Speech-to-text with Groq Whisper. Returns the verbose_json body (text and segments)."""
    if not transcription_configured(): raise AIUnavailable("Groq is not set up, so recordings cannot be transcribed.")
    if len(data) > MAX_AUDIO_BYTES: raise AIUnavailable("This recording is larger than Groq accepts for transcription (25 MB).")
    async with httpx.AsyncClient(timeout=180) as c:
        resp = await c.post(f"{BASE}/audio/transcriptions", headers=auth_headers(),
                            data={"model": stt_model(), "response_format": "verbose_json", "timestamp_granularities[]": "segment"},
                            files={"file": (filename, data, "application/octet-stream")})
    if resp.status_code == 429: raise AIUnavailable("Audio transcription was throttled by Groq. Try again in a minute.")
    if resp.status_code >= 400: raise AIUnavailable(_safe_error(resp).replace("request", "transcription"))
    return resp.json()

async def ping() -> tuple[bool, str]:
    """Tiny real chat request with the saved model, used by the Admin 'Test connections' button."""
    if not ai_configured(): return False, "Not configured"
    try:
        body = {"model": chat_model(), "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 8}
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.post(f"{BASE}/chat/completions", headers={**auth_headers(), "Content-Type": "application/json"}, json=body)
        if resp.status_code < 400: return True, f"Model {chat_model()} responded."
        return False, _safe_error(resp)
    except Exception: return False, "Groq could not be reached."
