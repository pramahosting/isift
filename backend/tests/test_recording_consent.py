"""Zoom-style recording disclaimer: participants are told, answer Continue/Leave, and the host can see who agreed."""
from tests.test_room_access import client, login, make, join  # noqa: F401

def _drain_until(w, typ, limit=12):
    for _ in range(limit):
        m = w.receive_json()
        if m.get("type") == typ: return m
    raise AssertionError(f"no {typ} message")

def test_consent_logged_and_reported(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False); code = r["code"]
    hws, hw = join(client, code, name="Host", token=tok); assert hw.receive_json()["host"] is True
    gws, gw = join(client, code, name="Gina"); w = gw.receive_json(); assert w["type"] == "welcome" and not w["recording"]
    hw.send_json({"type": "record", "on": True})
    rec = _drain_until(gw, "recording"); assert rec["on"] is True and rec["by"] == "Host"
    gw.send_json({"type": "consent", "accept": True})
    c = _drain_until(hw, "consent"); assert c["decision"] == "accepted" and c["name"] == "Gina"
    # someone who joins a recording already in progress is told in the welcome and is asked too
    lws, lw = join(client, code, name="Late"); w = lw.receive_json()
    assert w["type"] == "welcome" and w["recording"] is True and w["recorder"] is False and w["recorder_name"] == "Host"
    lw.send_json({"type": "consent", "accept": False, "joined": True})
    c = _drain_until(hw, "consent"); assert c["decision"] == "declined"
    # the recorder's own 'consent' is ignored
    hw.send_json({"type": "consent", "accept": True})
    rep = client.get(f"/api/v1/rooms/{code}/recording-consent", headers=h).json()
    assert {(x["name"], x["decision"], x["when_asked"]) for x in rep} == {("Gina", "accepted", "start"), ("Late", "declined", "join")}
    # only the host can read the report
    assert client.get(f"/api/v1/rooms/{code}/recording-consent").status_code in (401, 403)
    for s in (lws, gws, hws): s.__exit__(None, None, None)
