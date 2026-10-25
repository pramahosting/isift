"""isiftmail: free iSift addresses inside Commbox. The mail server is faked, so these tests need no Stalwart."""
import pytest
from test_room_access import client, login, signed_up       # same app and sign-up helpers as the other test files
from app.integrations import isiftmail as im, mail as mailer


def test_names_and_vacation_script():
    assert im.valid_name(" Jane.Doe@x.com ") == "jane.doe"
    for bad in ("ab", "a" * 31, "-jane", "jane-", "ja..ne", "has space", "admin", "postmaster", "isift-help", "bad$"):
        with pytest.raises(ValueError): im.valid_name(bad)
    s = im.vacation_script('Out of "office"', "Back soon.\nThanks", "2030-01-02", "2030-01-09")
    assert s.startswith('require ["vacation", "date", "relational"];') and 'allof(currentdate :value "ge" "date" "2030-01-02", currentdate :value "le" "date" "2030-01-09")' in s
    assert 'Out of \\"office\\"' in s and "\r\n" in s
    assert im.vacation_script("Away", "Gone").splitlines()[0] == 'require ["vacation"];'
    for args in (("Away", ""), ("Away", "x", "2030-1-2"), ("Away", "x", "2030-01-09", "2030-01-02")):
        with pytest.raises(ValueError): im.vacation_script(*args)


def test_managesieve_literal_is_sent_without_waiting():
    class F:
        def __init__(self): self.out = b""; self.lines = [b'OK "done"\r\n']
        def write(self, b): self.out += b
        def flush(self): pass
        def readline(self): return self.lines.pop(0)
    c = object.__new__(im._Sieve); c.f = F()
    c.cmd('PUTSCRIPT "isift-autoreply"', "require [\"vacation\"];\r\n")
    assert c.f.out == b'PUTSCRIPT "isift-autoreply" {23+}\r\nrequire ["vacation"];\r\n\r\n'


def test_stalwart_rest_calls(monkeypatch):
    import asyncio, httpx
    from app.core.config import settings
    for k, v in dict(isiftmail_domain="isiftmail.test", isiftmail_api_url="https://mail.isiftmail.test", isiftmail_api_user="admin", isiftmail_api_password="pw").items(): monkeypatch.setattr(settings, k, v)
    seen = []
    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path, req.headers.get("authorization", "")[:6], req.content))
        if req.method == "GET": return httpx.Response(200, json={"error": "notFound"}) if req.url.path.endswith("/ghost") else httpx.Response(200, json={"data": {"name": "jane"}})
        if req.method == "POST": return httpx.Response(200, json={"error": "fieldAlreadyExists", "field": "name"}) if b'"taken"' in req.content else httpx.Response(200, json={"data": 7})
        return httpx.Response(200, json={"data": None})
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    async def go():
        assert await im.exists("ghost") is False and await im.exists("jane") is True
        await im.create("jane", "s3cret", "Jane")
        with pytest.raises(mailer.MailError): await im.create("taken", "x")
        await im.set_password("jane", "n3w"); await im.remove("jane")
    asyncio.run(go())
    post = next(x for x in seen if x[0] == "POST"); assert post[2] == "Basic " [:6] and b'"emails":["jane@isiftmail.test"]' in post[3] and b'"type":"individual"' in post[3]
    patch = next(x for x in seen if x[0] == "PATCH"); assert b'"field":"secrets"' in patch[3] and b'"action":"set"' in patch[3]
    assert [x[0] for x in seen if x[0] == "DELETE"] == ["DELETE"]


@pytest.fixture()
def server(monkeypatch):
    """A made-up mail server: names taken, passwords, auto-reply scripts and drafts are kept in memory."""
    from app.core.config import settings
    for k, v in dict(isiftmail_domain="isiftmail.test", isiftmail_api_url="https://mail.isiftmail.test", isiftmail_imap_host="mail.isiftmail.test", isiftmail_smtp_host="mail.isiftmail.test").items(): monkeypatch.setattr(settings, k, v)
    st = {"names": {"taken"}, "pw": {}, "script": "unset", "drafts": [], "domains": set(), "dns": {}, "emails": {}}
    async def exists(n): return n in st["names"]
    async def create(n, pw, d="", address=""): st["names"].add(n); st["pw"][n] = pw; st["emails"][n] = address
    async def set_password(n, pw): st["pw"][n] = pw
    async def remove(n): st["names"].discard(n)
    async def apply(acct, script): st["script"] = script
    async def draft(acct, to, cc, subject, body, replace_uid=0): st["drafts"].append((to, cc, subject, body, replace_uid)); return 40 + len(st["drafts"])
    async def create_domain(d): st["domains"].add(d)
    async def create_dkim(d): pass
    async def remove_domain(d): st["domains"].discard(d)
    async def server_records(d): return [{"type": "TXT", "name": f"isift._domainkey.{d}", "value": "v=DKIM1; k=ed25519; p=AAAA"}] if d in st["domains"] else []
    async def lookup(name, rtype): return list(st["dns"].get((name, rtype), []))
    for name, fn in dict(exists=exists, create=create, set_password=set_password, remove=remove, apply_autoreply=apply, save_draft=draft, create_domain=create_domain, create_dkim=create_dkim,
                         remove_domain=remove_domain, server_dns_records=server_records, lookup=lookup).items(): monkeypatch.setattr(im, name, fn)
    return st


def _commbox_user(client, monkeypatch, email, first):
    h, _ = login(client)
    su = signed_up(client, monkeypatch, email, first, "Tester"); uh = {"Authorization": "Bearer " + su["access_token"]}
    client.get("/api/v1/account", headers=uh)
    uid = next(u["id"] for u in client.get("/api/v1/admin/users", headers=h).json() if u["email"] == email)
    assert client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"commbox": True}}, headers=h).status_code == 200      # Commbox needs a paid plan or the administrator's permission
    return h, uh


def test_isiftmail_whole_journey(client, monkeypatch, server):
    h, uh = _commbox_user(client, monkeypatch, "newbie@mycompany.example", "Newbie")
    s = client.get("/api/v1/isiftmail/status", headers=uh).json()
    assert s["available"] and s["eligible"] and s["domain"] == "isiftmail.test" and s["mailbox"] is None and s["mailboxes"] == []
    assert client.get("/api/v1/isiftmail/check?name=taken", headers=uh).json()["ok"] is False
    assert client.get("/api/v1/isiftmail/check?name=ab", headers=uh).json()["ok"] is False
    assert client.get("/api/v1/isiftmail/check?name=Newbie.One", headers=uh).json() == {"ok": True, "name": "newbie.one", "address": "newbie.one@isiftmail.test", "message": "Available."}
    r = client.post("/api/v1/isiftmail/create", json={"name": "newbie.one"}, headers=uh); assert r.status_code == 200, r.text
    made = r.json(); assert made["address"] == "newbie.one@isiftmail.test" and made["username"] == "newbie.one" and server["pw"]["newbie.one"] == made["password"]
    assert client.post("/api/v1/isiftmail/create", json={"name": "other.one"}, headers=uh).status_code == 409           # one free address each
    accts = client.get("/api/v1/mailbox/accounts", headers=uh).json()
    mine = next(a for a in accts["accounts"] if a["provider"] == "isiftmail"); assert mine["address"] == made["address"] and "isiftmail" not in accts["presets"]
    assert "password" not in str(mine)
    # managed by iSift: not edited or removed like a normal account
    assert client.patch(f"/api/v1/mailbox/accounts/{mine['id']}", json={"password": "x"}, headers=uh).status_code == 422
    assert client.delete(f"/api/v1/mailbox/accounts/{mine['id']}", headers=uh).status_code == 422
    # a normal account cannot pretend to be an isiftmail one
    assert client.post("/api/v1/mailbox/accounts", json={"provider": "isiftmail", "address": "x@y.org", "password": "p"}, headers=uh).status_code in (422, 502)
    # signature and auto-reply
    assert client.get("/api/v1/isiftmail/settings", headers=uh).json()["autoreply"]["on"] is False
    r = client.put("/api/v1/isiftmail/settings", json={"signature": "Newbie\r\nSydney"}, headers=uh); assert r.status_code == 200 and r.json()["signature"] == "Newbie\nSydney"
    assert server["script"] == "unset"                                                                                    # saving a signature leaves the auto-reply alone
    ar = {"on": True, "subject": "Away", "message": "Back on Monday.", "start": "2030-01-01", "end": "2030-01-05"}
    assert client.put("/api/v1/isiftmail/settings", json={"autoreply": ar}, headers=uh).status_code == 200 and "Back on Monday." in server["script"]
    assert client.put("/api/v1/isiftmail/settings", json={"autoreply": {**ar, "message": ""}}, headers=uh).status_code == 422
    g = client.get("/api/v1/isiftmail/settings", headers=uh).json(); assert g["autoreply"]["on"] is True and g["signature"] == "Newbie\nSydney"
    assert client.put("/api/v1/isiftmail/settings", json={"autoreply": {**ar, "on": False}}, headers=uh).status_code == 200 and server["script"] is None
    # drafts
    r = client.post("/api/v1/isiftmail/draft", json={"to": "a@example.com", "subject": "Hi", "body": "x", "replace_uid": 41}, headers=uh); assert r.status_code == 200 and r.json()["uid"] == 41
    assert server["drafts"][0][0] == ["a@example.com"] and server["drafts"][0][4] == 41
    assert client.post("/api/v1/isiftmail/draft", json={"to": "not-an-address"}, headers=uh).status_code == 422
    # password for other apps
    old = server["pw"]["newbie.one"]; r = client.post("/api/v1/isiftmail/password", headers=uh).json(); assert r["password"] != old and server["pw"]["newbie.one"] == r["password"]
    # close: needs the address typed, frees the mail server, and the name is held back
    assert client.request("DELETE", "/api/v1/isiftmail/mailbox", json={"confirm": "wrong"}, headers=uh).status_code == 422
    assert client.request("DELETE", "/api/v1/isiftmail/mailbox", json={"confirm": made["address"]}, headers=uh).status_code == 200
    assert "newbie.one" not in server["names"] and client.get("/api/v1/isiftmail/settings", headers=uh).status_code == 404
    assert client.get("/api/v1/isiftmail/check?name=newbie.one", headers=uh).json()["ok"] is False
    assert client.get("/api/v1/isiftmail/status", headers=uh).json()["eligible"] is True                              # and they could pick a new name (not the held one)


def test_isiftmail_is_open_to_everyone_one_free_address_each(client, monkeypatch, server):
    h, gh = _commbox_user(client, monkeypatch, "has.mail@gmail.com", "Gmailer")             # already has email elsewhere: still welcome
    s = client.get("/api/v1/isiftmail/status", headers=gh).json(); assert s["available"] and s["eligible"] is True and s["can_create"] is True
    r = client.post("/api/v1/isiftmail/create", json={"name": "gmailer1"}, headers=gh); assert r.status_code == 200, r.text
    assert client.post("/api/v1/isiftmail/create", json={"name": "gmailer2"}, headers=gh).status_code == 409             # one free address each
    s = client.get("/api/v1/isiftmail/status", headers=gh).json(); assert s["eligible"] is False and s["can_create"] is False and [m["address"] for m in s["mailboxes"]] == ["gmailer1@isiftmail.test"]
    assert client.get("/api/v1/isiftmail/status", headers=h).json()["eligible"] is True


def test_isiftmail_hidden_until_the_server_is_set_up(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "isiftmail_domain", "")
    h, uh = _commbox_user(client, monkeypatch, "nobody@mycompany.example", "Nobody")
    s = client.get("/api/v1/isiftmail/status", headers=uh).json(); assert s["available"] is False and s["eligible"] is False
    assert client.get("/api/v1/isiftmail/check?name=someone", headers=uh).status_code == 503
    assert client.post("/api/v1/isiftmail/create", json={"name": "someone"}, headers=uh).status_code == 503


def test_isiftmail_module_switch(client, monkeypatch, server):
    h, uh = _commbox_user(client, monkeypatch, "switch@mycompany.example", "Switcher")
    mods = {m["id"]: m for m in client.get("/api/v1/modules").json()["modules"]}; assert mods["isiftmail"]["enabled"] is True and "isiftmail" in mods["isiftmail"]["label"].lower()
    assert client.put("/api/v1/admin/modules", json={"enabled": {"isiftmail": False}}, headers=h).status_code == 200
    assert client.get("/api/v1/isiftmail/status", headers=uh).status_code == 403
    assert client.post("/api/v1/isiftmail/create", json={"name": "switch.me"}, headers=uh).status_code == 403
    assert client.get("/api/v1/mailbox/accounts", headers=uh).status_code == 200                                         # the rest of Commbox mail is untouched
    assert all(m["enabled"] for m in client.get("/api/v1/modules").json()["modules"] if m["id"] != "isiftmail")
    assert client.put("/api/v1/admin/modules", json={"enabled": {}}, headers=h).status_code == 200
    assert client.get("/api/v1/isiftmail/status", headers=uh).status_code == 200


def test_own_mail_server_may_be_on_a_private_address(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "calendar_feed_allow_private", False)
    with pytest.raises(mailer.MailError): mailer._check("127.0.0.1", 993)
    monkeypatch.setattr(settings, "isiftmail_imap_host", "127.0.0.1")
    mailer._check("127.0.0.1", 993)


def test_draft_is_appended_to_drafts_and_replaces_the_old_copy(monkeypatch):
    from app.integrations import mailbox as mb
    calls = []
    class Fake:
        def list(self): return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Drafts) "/" "Drafts"']
        def append(self, box, flags, when, raw): calls.append(("append", box, flags, raw)); return "OK", [b"[APPENDUID 1 77] Append completed"]
        def select(self, box): calls.append(("select", box)); return "OK", [b"1"]
        def uid(self, *a): calls.append(("uid",) + a); return "OK", []
        def expunge(self): calls.append(("expunge",)); return "OK", []
        def logout(self): pass
    monkeypatch.setattr(mb, "_connect", lambda acct: Fake())
    uid = im.save_draft_sync({"address": "jane@isiftmail.test"}, ["a@example.com"], [], "Hello", "Body text", replace_uid=70)
    assert uid == 77
    ap = next(c for c in calls if c[0] == "append"); assert ap[1] == '"Drafts"' and ap[2] == "\\Draft" and b"Subject: Hello" in ap[3] and b"To: a@example.com" in ap[3] and b"Body text" in ap[3]
    assert ("uid", "store", "70", "+FLAGS", "(\\Deleted)") in calls and ("expunge",) in calls


def _publish(server, dom, token, mx=True, spf=True):
    server["dns"][(f"_isiftmail-verify.{dom}", "TXT")] = [f"isiftmail-verify={token}"]
    if mx: server["dns"][(dom, "MX")] = ["mail.isiftmail.test"]
    if spf: server["dns"][(dom, "TXT")] = ["v=spf1 mx ~all"]


def test_own_domain_like_microsoft_365_at_godaddy(client, monkeypatch, server):
    h, uh = _commbox_user(client, monkeypatch, "pramod@prama-ai.com", "Pramod")
    api = lambda m, path, **kw: client.request(m, "/api/v1/isiftmail" + path, headers=uh, **kw)
    for bad in ("gmail.com", "isiftmail.test", "x.isiftmail.test", "not a domain", "localhost"): assert api("POST", "/domains", json={"domain": bad}).status_code == 422, bad
    assert api("POST", "/domains/check", json={"domain": "prama-ai.com"}).status_code == 404
    r = api("POST", "/domains", json={"domain": "Prama-AI.com"}); assert r.status_code == 200, r.text
    d = r.json(); assert d["domain"] == "prama-ai.com" and d["status"] == "pending"
    recs = {x["purpose"]: x for x in d["records"]}; token = recs["owner"]["value"].split("=")[1]
    assert recs["owner"]["name"] == "_isiftmail-verify.prama-ai.com" and recs["mx"]["value"] == "10 mail.isiftmail.test" and recs["spf"]["value"] == "v=spf1 mx ~all" and recs["dmarc"]["name"] == "_dmarc.prama-ai.com" and "dkim" not in recs
    assert (recs["autodiscover"]["type"], recs["autodiscover"]["name"], recs["autodiscover"]["value"]) == ("CNAME", "autodiscover.prama-ai.com", "mail.isiftmail.test")
    assert (recs["autoconfig"]["name"], recs["srv"]["type"], recs["srv"]["name"], recs["srv"]["value"]) == ("autoconfig.prama-ai.com", "SRV", "_autodiscover._tcp.prama-ai.com", "0 0 443 mail.isiftmail.test")
    # nothing can be made on a domain that is not proven yet
    assert api("POST", "/create", json={"name": "pramod", "domain": "prama-ai.com"}).status_code == 403
    assert api("GET", "/check?name=pramod&domain=prama-ai.com").status_code == 403
    r = api("POST", "/domains/check", json={"domain": "prama-ai.com"}).json(); assert r["verified"] is False and r["checks"]["owner"] is False and "prama-ai.com" not in server["domains"]
    _publish(server, "prama-ai.com", token, mx=False, spf=False)
    r = api("POST", "/domains/check", json={"domain": "prama-ai.com"}).json()
    assert r["verified"] is True and r["status"] == "verified" and "prama-ai.com" in server["domains"] and r["checks"]["owner"] and not r["checks"]["mx"] and "MX record" in r["message"]
    assert any(x["purpose"] == "dkim" for x in r["records"])                                                               # the mail server's signing key is shown once the domain exists there
    _publish(server, "prama-ai.com", token); server["dns"][("isift._domainkey.prama-ai.com", "TXT")] = ["v=DKIM1; k=ed25519; p=AAAA"]; server["dns"][("_dmarc.prama-ai.com", "TXT")] = ["v=DMARC1; p=none"]
    r = api("POST", "/domains/check", json={"domain": "prama-ai.com"}).json(); assert not r["checks"]["autodiscover"] and not r["checks"]["autoconfig"] and not r["checks"]["srv"]
    server["dns"][("autodiscover.prama-ai.com", "CNAME")] = ["mail.isiftmail.test"]; server["dns"][("autoconfig.prama-ai.com", "CNAME")] = ["mail.isiftmail.test"]; server["dns"][("_autodiscover._tcp.prama-ai.com", "SRV")] = ["0 0 443 mail.isiftmail.test"]
    r = api("POST", "/domains/check", json={"domain": "prama-ai.com"}).json(); assert all(r["checks"].values()) and len(r["checks"]) == 8, r["checks"]
    # Outlook, Thunderbird and phones can now find the settings from the address alone
    x = client.post("/autodiscover/autodiscover.xml", content='<Autodiscover><Request><EMailAddress>pramod@prama-ai.com</EMailAddress></Request></Autodiscover>')
    assert x.status_code == 200 and x.headers["content-type"].startswith("text/xml") and "<LoginName>pramod.prama-ai-com</LoginName>" in x.text and "<Server>mail.isiftmail.test</Server>" in x.text and "<Port>993</Port>" in x.text and "<Port>587</Port>" in x.text
    x = client.get("/mail/config-v1.1.xml?emailaddress=pramod@prama-ai.com"); assert x.status_code == 200 and "<username>%EMAILLOCALPART%.prama-ai-com</username>" in x.text and '<socketType>STARTTLS</socketType>' in x.text and "<hostname>mail.isiftmail.test</hostname>" in x.text
    assert client.get("/mail/config-v1.1.xml?emailaddress=pramod@isiftmail.test").text.count("<username>%EMAILLOCALPART%</username>") == 2
    assert client.get("/.well-known/autoconfig/mail/config-v1.1.xml?emailaddress=a@isiftmail.test").status_code == 200
    # the default address is on isiftmail, the other on the person's own domain
    assert api("POST", "/create", json={"name": "pramod"}).json()["address"] == "pramod@isiftmail.test"
    r = api("POST", "/create", json={"name": "pramod", "domain": "prama-ai.com"}); assert r.status_code == 200, r.text
    assert r.json()["address"] == "pramod@prama-ai.com" and r.json()["username"] == "pramod.prama-ai-com" and server["emails"]["pramod.prama-ai-com"] == "pramod@prama-ai.com"
    s = api("GET", "/status").json(); assert sorted(m["address"] for m in s["mailboxes"]) == ["pramod@isiftmail.test", "pramod@prama-ai.com"] and s["can_create"] is True and s["eligible"] is False
    assert api("GET", "/settings").json()["address"] == "pramod@isiftmail.test"
    aid = next(m["id"] for m in s["mailboxes"] if m["domain"] == "prama-ai.com")
    assert api("PUT", "/settings", json={"aid": aid, "signature": "Pramod, Prama AI"}).status_code == 200
    assert api("GET", f"/settings?aid={aid}").json()["signature"] == "Pramod, Prama AI" and api("GET", "/settings").json()["signature"] == ""        # each address has its own signature
    # staff: a mailbox for somebody who already has iSift, and one for somebody who has not signed up yet
    su = signed_up(client, monkeypatch, "sam@prama-ai.com", "Sam", "Staff"); sh = {"Authorization": "Bearer " + su["access_token"]}; client.get("/api/v1/account", headers=sh)
    uid = next(u["id"] for u in client.get("/api/v1/admin/users", headers=h).json() if u["email"] == "sam@prama-ai.com")
    assert client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"commbox": True}}, headers=h).status_code == 200
    r = api("POST", "/create", json={"name": "sam", "domain": "prama-ai.com", "for_email": "sam@prama-ai.com", "display_name": "Sam Staff"}).json()
    assert r["address"] == "sam@prama-ai.com" and r["assigned_to"] == "sam@prama-ai.com" and "appears in" in r["note"] and r["password"]
    mine = client.get("/api/v1/mailbox/accounts", headers=sh).json()["accounts"]; assert [a["address"] for a in mine if a["provider"] == "isiftmail"] == ["sam@prama-ai.com"]
    assert [a["address"] for a in client.get("/api/v1/mailbox/accounts", headers=uh).json()["accounts"] if a["address"].startswith("sam@")] == []     # not in the owner's own Mail
    r = api("POST", "/create", json={"name": "info", "domain": "prama-ai.com", "for_email": "later@prama-ai.com"}).json(); assert "when later@prama-ai.com signs in" in r["note"]
    assert api("POST", "/create", json={"name": "x1", "for_email": "later@prama-ai.com"}).status_code in (409, 422)                                          # for others: only on your own domain
    assert api("POST", "/create", json={"name": "x2", "domain": "prama-ai.com", "for_email": "not-an-email"}).status_code == 422
    lst = api("GET", "/domains/mailboxes?domain=prama-ai.com").json()["mailboxes"]
    assert [(m["address"], m["status"], m["yours"]) for m in lst] == [("info@prama-ai.com", "waiting", False), ("pramod@prama-ai.com", "active", True), ("sam@prama-ai.com", "active", False)]
    su2 = signed_up(client, monkeypatch, "later@prama-ai.com", "Later", "Staff"); lh = {"Authorization": "Bearer " + su2["access_token"]}; client.get("/api/v1/account", headers=lh)
    uid2 = next(u["id"] for u in client.get("/api/v1/admin/users", headers=h).json() if u["email"] == "later@prama-ai.com")
    assert client.patch(f"/api/v1/admin/users/{uid2}", json={"limits": {"commbox": True}}, headers=h).status_code == 200
    assert client.get("/api/v1/isiftmail/status", headers=lh).json()["mailboxes"][0]["address"] == "info@prama-ai.com"                                  # appears the first time they look
    assert [m["status"] for m in api("GET", "/domains/mailboxes?domain=prama-ai.com").json()["mailboxes"]] == ["active"] * 3
    # a staff member cannot close a mailbox the administrator runs; the administrator can reset the password and close it
    sam = client.get("/api/v1/isiftmail/status", headers=sh).json()["mailboxes"][0]
    assert client.request("DELETE", "/api/v1/isiftmail/mailbox", json={"aid": sam["id"], "confirm": sam["address"]}, headers=sh).status_code == 403
    old = server["pw"]["sam.prama-ai-com"]; r = api("POST", "/domains/mailboxes/password", json={"address": "sam@prama-ai.com"}).json(); assert r["password"] != old and server["pw"]["sam.prama-ai-com"] == r["password"]
    assert api("DELETE", "/domains", json={"domain": "prama-ai.com"}).status_code == 409                                                               # mailboxes still on it
    assert api("DELETE", "/domains/mailboxes", json={"address": "sam@prama-ai.com", "confirm": "no"}).status_code == 422
    assert api("DELETE", "/domains/mailboxes", json={"address": "sam@prama-ai.com", "confirm": "sam@prama-ai.com"}).status_code == 200
    assert "sam.prama-ai-com" not in server["names"] and client.get("/api/v1/isiftmail/status", headers=sh).json()["mailboxes"] == []
    assert api("POST", "/domains/mailboxes/password", json={"address": "nobody@prama-ai.com"}).status_code == 404
    # somebody else cannot manage this domain's mailboxes or take the domain
    assert client.get("/api/v1/isiftmail/domains/mailboxes?domain=prama-ai.com", headers=sh).status_code == 404
    assert client.post("/api/v1/isiftmail/domains", json={"domain": "prama-ai.com"}, headers=sh).status_code == 409
    for a in ("info@prama-ai.com", "pramod@prama-ai.com"): assert api("DELETE", "/domains/mailboxes", json={"address": a, "confirm": a}).status_code == 200
    assert api("DELETE", "/domains", json={"domain": "prama-ai.com"}).status_code == 200 and "prama-ai.com" not in server["domains"] and api("GET", "/domains").json()["domains"] == []


def test_two_people_may_claim_a_domain_but_only_the_one_who_proves_it_wins(client, monkeypatch, server):
    h, a = _commbox_user(client, monkeypatch, "one@mycompany.example", "One")
    su = signed_up(client, monkeypatch, "two@other.example", "Two", "Person"); b = {"Authorization": "Bearer " + su["access_token"]}; client.get("/api/v1/account", headers=b)
    uid = next(u["id"] for u in client.get("/api/v1/admin/users", headers=h).json() if u["email"] == "two@other.example")
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"commbox": True}}, headers=h)
    ta = client.post("/api/v1/isiftmail/domains", json={"domain": "shared-name.com"}, headers=a).json()["records"][0]["value"].split("=")[1]
    tb = client.post("/api/v1/isiftmail/domains", json={"domain": "shared-name.com"}, headers=b).json()["records"][0]["value"].split("=")[1]
    assert ta != tb
    _publish(server, "shared-name.com", tb)                                                                           # only the second person controls the DNS
    assert client.post("/api/v1/isiftmail/domains/check", json={"domain": "shared-name.com"}, headers=a).json()["verified"] is False
    assert client.post("/api/v1/isiftmail/domains/check", json={"domain": "shared-name.com"}, headers=b).json()["verified"] is True
    _publish(server, "shared-name.com", ta)
    assert client.post("/api/v1/isiftmail/domains/check", json={"domain": "shared-name.com"}, headers=a).status_code == 409        # too late: already proven by someone else


def test_autosetup_documents_only_for_hosted_domains(client, monkeypatch, server):
    assert client.get("/mail/config-v1.1.xml?emailaddress=someone@isiftmail.test").status_code == 200
    for bad in ("someone@gmail.com", "someone@unverified-co.com", "not-an-address", ""): assert client.get(f"/mail/config-v1.1.xml?emailaddress={bad}").status_code == 404, bad
    assert client.post("/autodiscover/autodiscover.xml", content="<x/>").status_code == 404
    assert "<EMailAddress>a&amp;b@isiftmail.test</EMailAddress>" not in client.post("/autodiscover/autodiscover.xml", content="<EMailAddress>a&b@isiftmail.test</EMailAddress>").text      # never echoes unescaped input
    h, uh = _commbox_user(client, monkeypatch, "owner@mycompany.example", "Owner")
    client.post("/api/v1/isiftmail/domains", json={"domain": "unverified-co.com"}, headers=uh)
    assert client.get("/mail/config-v1.1.xml?emailaddress=someone@unverified-co.com").status_code == 404                           # a domain that is not proven is not answered
    assert client.put("/api/v1/admin/modules", json={"enabled": {"isiftmail": False}}, headers=h).status_code == 200
    assert client.get("/mail/config-v1.1.xml?emailaddress=someone@isiftmail.test").status_code == 404                              # and nothing is answered while the module is off


def test_autosetup_name_can_be_set_apart_from_the_mail_name(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "isiftmail_imap_host", "mail.isiftmail.test")
    assert im.autoconfig_host() == "mail.isiftmail.test"
    monkeypatch.setattr(settings, "isiftmail_autoconfig_host", "Autoconfig.IsiftMail.test.")
    assert im.autoconfig_host() == "autoconfig.isiftmail.test"
    assert {r["purpose"]: r["value"] for r in im.dns_records("co.example", "t")}["srv"] == "0 0 443 autoconfig.isiftmail.test"


def test_dns_answers_are_read_correctly(monkeypatch):
    import types, dns.resolver
    answers = {("a.example.", "CNAME"): [types.SimpleNamespace(target="Mail.Isiftmail.Test.")],
               ("s.example.", "SRV"): [types.SimpleNamespace(priority=0, weight=0, port=443, target="Mail.Isiftmail.Test.")],
               ("m.example.", "MX"): [types.SimpleNamespace(exchange="Mail.Isiftmail.Test.")],
               ("t.example.", "TXT"): [types.SimpleNamespace(strings=[b"v=spf1 ", b"mx ~all"])]}
    def fake(name, rtype, lifetime=6):
        if (name + ".", rtype) in answers or (name, rtype) in answers: return answers.get((name + ".", rtype)) or answers[(name, rtype)]
        raise dns.resolver.NXDOMAIN()
    monkeypatch.setattr(dns.resolver, "resolve", fake)
    assert im._resolve("a.example", "CNAME") == ["mail.isiftmail.test"] and im._resolve("s.example", "SRV") == ["0 0 443 mail.isiftmail.test"]
    assert im._resolve("m.example", "MX") == ["mail.isiftmail.test"] and im._resolve("t.example", "TXT") == ["v=spf1 mx ~all"] and im._resolve("none.example", "TXT") == []


def test_spam_controls(client, monkeypatch, server):
    from app.core.config import settings
    from app.integrations import mailbox as mb
    for k, v in dict(isiftmail_send_per_hour=2, isiftmail_max_recipients=3, isiftmail_complaint_limit=2, isiftmail_hook_secret="s3", isiftmail_new_per_day=1).items(): monkeypatch.setattr(settings, k, v)
    from app.api import routes_isiftmail as ri; ri._NEW_BY_NET.clear()      # earlier tests used the same network address
    sent = []
    async def fake_send(a, to, cc, subject, body, reply=""): sent.append(to)
    monkeypatch.setattr(mb, "send", fake_send)
    h, uh = _commbox_user(client, monkeypatch, "spammy@mycompany.example", "Spammy")
    client.put("/api/v1/admin/modules", json={"enabled": {"isiftmail": True, "mail": True}}, headers=h)     # an earlier test may have left it off
    made = client.post("/api/v1/isiftmail/create", json={"name": "spammy.one"}, headers=uh); assert made.status_code == 200, made.text; addr = made.json()["address"]
    aid = next(a for a in client.get("/api/v1/mailbox/accounts", headers=uh).json()["accounts"] if a["provider"] == "isiftmail")["id"]
    send = lambda to="a@example.com": client.post(f"/api/v1/mailbox/accounts/{aid}/send", json={"to": to, "subject": "s", "body": "b"}, headers=uh)
    assert send().status_code == 200 and send().status_code == 200
    assert send().status_code == 429                                                                           # hourly limit
    assert len(sent) == 2
    # bulk sign-ups: one network address may only open a few new addresses a day
    import time
    from app.api import routes_isiftmail as ri
    for k in list(ri._NEW_BY_NET): ri._NEW_BY_NET[k] = [time.time()] * 3
    h2, uh2 = _commbox_user(client, monkeypatch, "bulk@mycompany.example", "Bulk")
    assert client.post("/api/v1/isiftmail/create", json={"name": "bulk.one"}, headers=uh2).status_code == 429
    # too many people in one message
    monkeypatch.setattr(settings, "isiftmail_send_per_hour", 50)
    assert send("a@x.org, b@x.org, c@x.org, d@x.org").status_code == 429
    # relay notices need the secret
    ev = {"events": [{"type": "Complaint", "from": addr}]}
    assert client.post("/api/v1/isiftmail/hooks/relay?secret=bad", json=ev).status_code == 403
    assert client.post("/api/v1/isiftmail/hooks/relay", json=ev).status_code == 403
    r = client.post("/api/v1/isiftmail/hooks/relay?secret=s3", json=ev).json(); assert r["handled"] == 1 and r["events"][0]["suspended"] is False
    assert client.post("/api/v1/isiftmail/hooks/relay?secret=s3", json={"type": "bounce", "bounceType": "Transient", "from": addr}).json()["handled"] == 0     # soft bounces are ignored
    before = server["pw"]["spammy.one"]
    assert client.post("/api/v1/isiftmail/report", json={"address": addr}).status_code == 200                      # a public report counts as the second complaint
    assert server["pw"]["spammy.one"] != before                                                                    # login locked on the mail server
    assert send().status_code == 403                                                                               # and iSift will not send
    # the administrator sees it, and can restore it
    assert client.get("/api/v1/admin/isiftmail/mailboxes", headers=uh).status_code == 403
    box = next(b for b in client.get("/api/v1/admin/isiftmail/mailboxes", headers=h).json()["mailboxes"] if b["address"] == addr)
    assert box["suspended"] and box["complaints"] == 2 and box["sent_24h"] == 2
    assert client.post("/api/v1/admin/isiftmail/unsuspend", json={"address": addr}, headers=h).status_code == 200
    assert server["pw"]["spammy.one"] == before and send().status_code == 200
    assert client.post("/api/v1/admin/isiftmail/suspend", json={"address": addr, "reason": "test"}, headers=h).status_code == 200 and send().status_code == 403
    assert client.post("/api/v1/isiftmail/report", json={"address": "nobody@elsewhere.org"}).status_code == 200      # unknown senders are accepted quietly
    assert client.post("/api/v1/isiftmail/report", json={"address": "nonsense"}).status_code == 422
