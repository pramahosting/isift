"""Give control of a shared file: the sharer lets one person page and scroll it; only the controller's commands reach the sharer."""
import time
from test_room_access import client, login, make, join


def _next(w, kind, n=20, holder="any"):
    for _ in range(n):
        m = w.receive_json()
        if m.get("type") == kind and (holder == "any" or m.get("holder") == holder): return m
    raise AssertionError(f"no {kind} message")


def test_give_and_take_control(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False)
    wss = []
    ws1, host = join(client, r["code"], name="Host", token=tok); hid = _next(host, "welcome")["id"]
    ws2, a = join(client, r["code"], name="Ann"); aid = _next(a, "welcome")["id"]
    ws3, b = join(client, r["code"], name="Bo"); bid = _next(b, "welcome")["id"]
    wss = [ws1, ws2, ws3]
    try:
        _run(host, a, b, hid, aid, bid)
    finally:
        for ws in wss: ws.__exit__(None, None, None)


def _run(host, a, b, hid, aid, bid):
    host.send_json({"type": "state", "mic": False, "cam": False, "screen": True})
    a.send_json({"type": "ctl_do", "sharer": hid, "act": "page", "d": 1})                    # nobody has control yet: nothing happens
    host.send_json({"type": "ctl_give", "to": aid})
    m = _next(a, "ctl"); assert m["holder"] == aid and m["sharer"] == hid and m["name"] == "Ann"
    b.send_json({"type": "ctl_do", "sharer": hid, "act": "page", "d": 1})                    # someone else may not
    a.send_json({"type": "ctl_do", "sharer": hid, "act": "page", "d": 5})
    got = _next(host, "ctl-do"); assert got["act"] == "page" and got["v"] == 1.0 and got["by"] == aid   # only Ann's command arrived, and the step is one page
    time.sleep(0.1); a.send_json({"type": "ctl_do", "sharer": hid, "act": "scroll", "dy": 99999})
    got = _next(host, "ctl-do"); assert got["act"] == "scroll" and got["v"] == 3000.0
    a.send_json({"type": "ctl_give", "to": bid})                                             # a controller cannot pass control on
    host.send_json({"type": "ctl_take"}); m = _next(a, "ctl", holder=None); assert m["holder"] is None
    a.send_json({"type": "ctl_do", "sharer": hid, "act": "page", "d": 1})
    host.send_json({"type": "ctl_give", "to": bid}); assert _next(b, "ctl", holder=bid)["holder"] == bid
    host.send_json({"type": "state", "mic": False, "cam": False, "screen": False})           # sharing stopped: control goes back
    assert _next(b, "ctl", holder=None)["holder"] is None
