from app.integrations import mailbox as mb


class FakeIMAP:
    def list(self): return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Sent"']
    def select(self, name, readonly=True): return "OK", [b"1"]
    def uid(self, cmd, *a):
        if cmd == "search": return "OK", [b"1 2"]
        h1 = b"From: Asha Rao <asha@client.com>\r\nTo: me@x.com\r\nCc: Bob <bob@y.org>\r\n\r\n"
        h2 = b"From: noreply@shop.com\r\nTo: me@x.com, Asha Rao <asha@client.com>\r\n\r\n"
        return "OK", [(b"1 (UID 1 BODY[HEADER.FIELDS (FROM TO CC)] {1}", h1), b")", (b"2 (UID 2 BODY[HEADER.FIELDS (FROM TO CC)] {1}", h2), b")"]
    def logout(self): pass


def test_correspondents_skip_self_and_noreply(monkeypatch):
    monkeypatch.setattr(mb, "_connect", lambda acct: FakeIMAP())
    out = mb.correspondents_sync({"address": "me@x.com"})
    got = {p["email"]: p["name"] for p in out}
    assert got.get("asha@client.com") == "Asha Rao" and got.get("bob@y.org") == "Bob"
    assert "me@x.com" not in got and "noreply@shop.com" not in got
    assert out[0]["email"] == "asha@client.com"          # most frequent first
