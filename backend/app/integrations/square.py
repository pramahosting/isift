"""Square REST API (server side only): customers, cards on file and payments. Mirrors the AccFino billing client."""
import uuid
import httpx
from app.core.config import settings

VERSION = "2024-10-17"
HOSTS = {"sandbox": "https://connect.squareupsandbox.com", "production": "https://connect.squareup.com"}
SDK = {"sandbox": "https://sandbox.web.squarecdn.com/v1/square.js", "production": "https://web.squarecdn.com/v1/square.js"}
_transport = None          # tests install an httpx.MockTransport here

class SquareError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code); self.code, self.detail = code, detail

def key() -> str: return uuid.uuid4().hex
def env() -> str: return settings.square_environment if settings.square_environment in HOSTS else "sandbox"
def configured() -> bool: return bool(settings.square_access_token and settings.square_application_id and settings.square_location_id)
def missing() -> list[str]:
    return [n for n, v in (("Access token", settings.square_access_token), ("Application ID", settings.square_application_id), ("Location ID", settings.square_location_id)) if not v]

async def _call(method: str, path: str, body: dict | None = None) -> dict:
    if not settings.square_access_token: raise SquareError("not_configured", "Square is not set up.")
    try:
        async with httpx.AsyncClient(timeout=25, transport=_transport, base_url=HOSTS[env()]) as c:
            r = await c.request(method, path, json=body, headers={"Authorization": "Bearer " + settings.square_access_token, "Square-Version": VERSION})
    except httpx.HTTPError as exc:
        raise SquareError("network", f"Could not reach Square ({type(exc).__name__}).")
    try: data = r.json()
    except ValueError: data = {}
    if r.status_code >= 400 or data.get("errors"):
        errs = data.get("errors") or [{}]
        raise SquareError(str(errs[0].get("code") or r.status_code), str(errs[0].get("detail") or errs[0].get("code") or f"Square returned HTTP {r.status_code}")[:280])
    return data

async def get_location() -> dict: return (await _call("GET", f"/v2/locations/{settings.square_location_id}")).get("location", {})

async def create_customer(*, idempotency_key: str, email: str, name: str, reference_id: str) -> dict:
    return (await _call("POST", "/v2/customers", {"idempotency_key": idempotency_key, "email_address": email, "given_name": name[:100], "reference_id": reference_id})).get("customer", {})

async def create_card(*, source_id: str, customer_id: str, idempotency_key: str) -> dict:
    return (await _call("POST", "/v2/cards", {"idempotency_key": idempotency_key, "source_id": source_id, "card": {"customer_id": customer_id}})).get("card", {})

async def disable_card(card_id: str) -> dict: return await _call("POST", f"/v2/cards/{card_id}/disable", {})

async def create_payment(*, card_id: str, customer_id: str, amount_cents: int, idempotency_key: str, email: str, note: str, reference_id: str) -> dict:
    return (await _call("POST", "/v2/payments", {"idempotency_key": idempotency_key, "source_id": card_id, "customer_id": customer_id, "location_id": settings.square_location_id,
        "autocomplete": True, "amount_money": {"amount": amount_cents, "currency": settings.square_currency}, "buyer_email_address": email or None, "note": note[:480], "reference_id": reference_id[:40]})).get("payment", {})

async def refund_payment(*, payment_id: str, amount_cents: int, idempotency_key: str, reason: str) -> dict:
    return (await _call("POST", "/v2/refunds", {"idempotency_key": idempotency_key, "payment_id": payment_id, "amount_money": {"amount": amount_cents, "currency": settings.square_currency}, "reason": reason[:190]})).get("refund", {})
