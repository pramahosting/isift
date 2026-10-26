"""A shared file everyone sees live: the owner lets one person at a time edit it, and edits reach everyone at once."""
import time
from test_room_access import client, login, make, join


def _next(w, kind, n=30, **want):
    for _ in range(n):
        m = w.receive_json()
        if m.get("type") == kind and all(m.get(k) == v for k, v in want.items()): return m
    raise AssertionError(f"no {kind} message {want}")


def test_shared_file_editing_turns(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False)
    ws1, host = join(client, r["code"], name="Host", token=tok); hid = _next(host, "welcome")["id"]
    ws2, a = join(client, r["code"], name="Ann"); aid = _next(a, "welcome")["id"]
    ws3, b = join(client, r["code"], name="Bo"); bid = _next(b, "welcome")["id"]
    try:
        host.send_json({"type": "collab_open", "kind": "doc", "title": "Agenda", "content": "1. Welcome"})
        for w in (a, b): m = _next(w, "collab", open=True); assert m["content"] == "1. Welcome" and m["holder"] == hid and m["owner_name"] == "Host" and m["kind"] == "doc"
        a.send_json({"type": "collab_edit", "content": "Ann was here", "rev": 1})                     # nobody but the editor may change it
        assert _next(a, "collab-holder", holder=hid)
        a.send_json({"type": "collab_ask"}); m = _next(host, "collab-ask"); assert m["id"] == aid and m["name"] == "Ann"      # a request to edit reaches the owner
        host.send_json({"type": "collab_give", "to": aid}); assert _next(b, "collab-holder")["holder"] == aid
        time.sleep(0.1); a.send_json({"type": "collab_edit", "content": "1. Welcome\n2. Budget", "rev": 1})
        m = _next(host, "collab-edit"); assert m["content"].endswith("Budget") and m["rev"] == 2 and m["by"] == aid
        assert _next(b, "collab-edit")["rev"] == 2
        b.send_json({"type": "collab_give", "to": bid}); b.send_json({"type": "collab_take"}); b.send_json({"type": "collab_close"})   # only the owner or a host may hand it on, take it back or close it
        host.send_json({"type": "collab_take"}); assert _next(a, "collab-holder", holder=hid)
        ws4, c = join(client, r["code"], name="Late"); _next(c, "welcome")                           # someone who joins later sees the current file
        m = _next(c, "collab", open=True); assert m["content"].endswith("Budget") and m["rev"] == 2
        ws4.__exit__(None, None, None)
        host.send_json({"type": "collab_close"}); assert _next(a, "collab", open=False)["reason"] == "closed"
        host.send_json({"type": "collab_open", "kind": "nonsense", "content": ""}); assert _next(host, "collab-denied")
        host.send_json({"type": "collab_open", "kind": "board", "title": "B", "content": "x" * 1_600_000}); assert _next(host, "collab-denied")["reason"] == "too_big"
    finally:
        for ws in (ws1, ws2, ws3): ws.__exit__(None, None, None)


def test_owner_leaving_closes_and_editor_leaving_returns_it(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False)
    ws1, host = join(client, r["code"], name="Host", token=tok); hid = _next(host, "welcome")["id"]
    ws2, a = join(client, r["code"], name="Ann"); aid = _next(a, "welcome")["id"]
    try:
        a.send_json({"type": "collab_open", "kind": "board", "title": "Sketch", "content": "{}"}); assert _next(host, "collab", open=True)["owner"] == aid
        a.send_json({"type": "collab_give", "to": hid}); assert _next(a, "collab-holder", holder=hid)
        ws1.__exit__(None, None, None)                                                                # the editor leaves: it goes back to the owner
        assert _next(a, "collab-holder", holder=aid)
    finally:
        ws2.__exit__(None, None, None)
    ws3, host2 = join(client, r["code"], name="Host2", token=tok); _next(host2, "welcome")
    ws3.__exit__(None, None, None)
