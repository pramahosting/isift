"""The site assistant must always answer from the CURRENT plan settings, and must agree with the Pricing page."""
import re, pathlib
from tests.test_room_access import client, login   # noqa: F401  (fixtures)

PRICING = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "Pricing.tsx"

def _capture(monkeypatch):
    from app.core.config import settings
    from app.services import groq
    seen = {}
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": "ok"}}]}
    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None): seen["system"] = json["messages"][0]["content"]; return R()
    monkeypatch.setattr(groq.httpx, "AsyncClient", C); monkeypatch.setattr(settings, "groq_api_key", "gsk_x")
    return seen

def _ask(client, q): return client.post("/api/v1/support/chat", json={"messages": [{"role": "user", "content": q}]}).json()

def _plan_line(system, name):
    return next(l for l in system.splitlines() if l.startswith(f"- {name}:"))

def test_assistant_matches_the_pricing_page_and_plan_settings(client, monkeypatch):
    seen = _capture(monkeypatch); _ask(client, "Does the free plan include Commbox?")
    s = seen["system"]
    basic, std = _plan_line(s, "Basic"), _plan_line(s, "Standard")
    assert "Does NOT include" in basic and "Commbox" in basic.split("Does NOT include")[1] and "Commbox" in std.split("Includes")[1] and "Does NOT include" not in std
    # the Pricing page row says the same thing
    row = re.search(r"\['Open room, Commbox, booking pages','(\w+)','(\w+)','(\w+)'\]", PRICING.read_text())
    assert row and row.groups() == ("No", "Yes", "Yes")
    assert "Headstart Finances Australia Pty Ltd" in s and "88 656 265 860" in s and "hsfinances.com.au" in s

def test_plain_answer_without_groq_says_commbox_is_not_in_basic(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "groq_api_key", "")
    r = _ask(client, "does the free plan have commbox")["reply"]
    assert "Standard and Business" in r and "not in Basic" in r
    who = _ask(client, "Who runs this company?")["reply"]
    assert "Headstart Finances Australia Pty Ltd" in who and "hsfinances.com.au" in who

def test_assistant_follows_a_plan_change_made_by_the_administrator(client, monkeypatch):
    ah, _ = login(client); seen = _capture(monkeypatch)
    assert client.put("/api/v1/admin/plan-config", json={"plan": "basic", "limits": {"commbox": True}}, headers=ah).status_code == 200
    try:
        _ask(client, "what is in basic?"); line = _plan_line(seen["system"], "Basic")
        assert "Commbox" in line.split("Includes")[1] and "Commbox" not in line.split("Does NOT include")[1]
    finally:
        client.put("/api/v1/admin/plan-config", json={"plan": "basic", "limits": {"commbox": None}}, headers=ah)
    _ask(client, "what is in basic?"); assert "Commbox" in _plan_line(seen["system"], "Basic").split("Does NOT include")[1]
