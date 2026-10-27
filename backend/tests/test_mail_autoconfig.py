import asyncio
from app.integrations import mail_autoconfig as ac


def _run(monkeypatch, mx, cfg=None, resolves=True, addr="u@example.org"):
    monkeypatch.setattr(ac, "_mx", lambda d: mx)
    async def h(d): return cfg
    monkeypatch.setattr(ac, "_http_config", h); monkeypatch.setattr(ac, "_resolves", lambda host: resolves)
    return asyncio.run(ac.detect(addr))


def test_known_hosts_from_mx(monkeypatch):
    r = _run(monkeypatch, ["smtp.secureserver.net", "mailstore1.secureserver.net"])
    assert (r["imap_host"], r["imap_port"], r["smtp_host"], r["smtp_port"]) == ("imap.secureserver.net", 993, "smtpout.secureserver.net", 465)
    assert _run(monkeypatch, ["mx1.titan.email"])["smtp_host"] == "smtp.titan.email"
    assert _run(monkeypatch, ["mx.zoho.com.au"])["imap_host"] == "imap.zoho.com.au"


def test_google_and_microsoft_use_sign_in(monkeypatch):
    assert _run(monkeypatch, ["aspmx.l.google.com"])["oauth"] == "google"
    assert _run(monkeypatch, ["x-com.mail.protection.outlook.com"])["oauth"] == "microsoft"
    assert _run(monkeypatch, [], addr="a@gmail.com")["oauth"] == "google"


def test_autoconfig_then_guess_then_nothing(monkeypatch):
    r = _run(monkeypatch, [], {"imap": ("imap.a.com", 993), "smtp": ("smtp.a.com", 587), "label": "A"})
    assert r["source"] == "autoconfig" and r["smtp_port"] == 587
    g = _run(monkeypatch, []); assert g["guess"] and g["imap_host"] == "imap.example.org"
    assert _run(monkeypatch, [], resolves=False)["found"] is False
    assert _run(monkeypatch, [], addr="bad")["found"] is False


def test_xml_parse():
    d = ac._from_xml('<clientConfig><emailProvider><incomingServer type="imap"><hostname>imap.foo.com</hostname><port>993</port></incomingServer><outgoingServer type="smtp"><hostname>smtp.foo.com</hostname><port>587</port></outgoingServer></emailProvider></clientConfig>')
    assert d["imap"] == ("imap.foo.com", 993) and d["smtp"] == ("smtp.foo.com", 587)
    assert ac._from_xml("<nope") is None
