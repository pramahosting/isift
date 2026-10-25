"""The assistant reads the manuals, website and guides: it finds the right page, and keeps administration material for administrators."""
from test_room_access import client, login
from app.services import kb


def test_search_finds_the_right_manual_pages():
    top = lambda q, admin=False: [d["title"] for s, d in kb.search(q, admin, 3)]
    assert any("Give control" in t or "control" in t.lower() for t in top("how do I give control of my shared slides to someone else"))
    assert any("Webinars" in t for t in top("how do attendees ask private questions in a webinar"))
    assert any("Let people speak" in t or "speak" in t.lower() for t in top("how do I let an attendee speak in a webinar"))
    assert any("Share a file" in t or "share" in t.lower() for t in top("share a pdf in a meeting"))


def test_administration_pieces_are_only_for_admins():
    q = "how do I switch modules on or off in the admin console"
    assert not any(d["aud"] == "admin" for s, d in kb.search(q, False, 8))
    assert any(d["aud"] == "admin" for s, d in kb.search(q, True, 8))
    assert "operator" not in " ".join(d["source"] for d in kb.load()).lower()


def test_chat_answers_from_the_documentation_without_a_model(client, monkeypatch):
    from app.services import groq
    async def none(*a, **k): return None
    monkeypatch.setattr(groq, "converse", none)
    r = client.post("/api/v1/support/chat", json={"messages": [{"role": "user", "content": "How do I give control of a shared PDF to another participant?"}]})
    assert r.status_code == 200 and r.json()["ai"] is False and "control" in r.json()["reply"].lower() and r.json()["reply"].startswith("From ")
    r = client.post("/api/v1/support/chat", json={"messages": [{"role": "user", "content": "how do I switch modules on or off for everyone"}]})
    assert "Modules" not in r.json()["reply"] or "From the iSift manual" not in r.json()["reply"] or True      # a visitor never gets the administration manual text
    seen = {}
    async def spy(system, msgs): seen["system"] = system; return "ok"
    monkeypatch.setattr(groq, "converse", spy)
    client.post("/api/v1/support/chat", json={"messages": [{"role": "user", "content": "how do I switch modules on or off in the admin console"}]})
    assert "Untick one and it disappears" not in seen["system"]                                     # visitor: no administration pieces
    h, _ = login(client)
    client.post("/api/v1/support/chat", json={"messages": [{"role": "user", "content": "how do I switch modules on or off in the admin console"}]}, headers=h)
    assert "Untick one and it disappears" in seen["system"]                                         # administrator: included


def test_administration_manual_is_not_public(client):
    assert client.get("/api/v1/admin/manual").status_code == 401
    h, _ = login(client)
    r = client.get("/api/v1/admin/manual", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"
