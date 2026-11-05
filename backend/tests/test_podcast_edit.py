"""Podcast video editor (real ffmpeg) and one-click YouTube posting (Google's servers are replaced by a fake)."""
import json, shutil, subprocess, time
from urllib.parse import urlsplit, parse_qs
import httpx
import pytest
from tests.test_room_access import client, login   # noqa: F401  (fixtures)

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")

def ff(*args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True); assert r.returncode == 0, r.stderr

@pytest.fixture()
def media(tmp_path):
    ff("-f", "lavfi", "-i", "testsrc=d=10:s=320x180:r=25", "-f", "lavfi", "-i", "sine=f=440:d=10", "-c:v", "libvpx", "-b:v", "300k", "-c:a", "libopus", "-shortest", str(tmp_path / "main.webm"))
    ff("-f", "lavfi", "-i", "smptebars=d=2:s=320x180:r=25", "-f", "lavfi", "-i", "sine=f=880:d=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(tmp_path / "clip.mp4"))
    ff("-f", "lavfi", "-i", "sine=f=200:d=3", str(tmp_path / "vo.wav"))
    ff("-f", "lavfi", "-i", "sine=f=300:d=4", "-c:a", "libopus", str(tmp_path / "talk.webm"))
    return tmp_path

@pytest.fixture()
def env(client, monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path / "data"))
    ah, _ = login(client); return ah

def upload(client, h, path, title="Ep", w=320, hh=180, video=True):
    data = {"title": title, "duration_s": "10", "width": str(w if video else 0), "height": str(hh if video else 0), "audio_kbps": "256"}
    r = client.post("/api/v1/podcasts", headers=h, data=data, files={"master": ("m.webm", path.read_bytes(), "video/webm")}); assert r.status_code == 200, r.text
    g = next(x for x in client.get("/api/v1/podcasts", headers=h).json() if x["group_id"] == r.json()["group_id"]); return g

def wait(client, h, jid, secs=40):
    end = time.time() + secs
    while time.time() < end:
        j = client.get(f"/api/v1/podcasts/jobs/{jid}", headers=h).json()
        if j["status"] != "working": return j
        time.sleep(0.3)
    raise AssertionError(f"job did not finish: {j}")

def dur(client, h, gid):
    g = next(x for x in client.get("/api/v1/podcasts", headers=h).json() if x["group_id"] == gid); return g["tracks"][0]

def test_open_preview_is_seekable_and_signed(client, env, media):
    g = upload(client, env, media / "main.webm"); rid = g["tracks"][0]["id"]
    o = client.post(f"/api/v1/podcasts/edit/open/{rid}", headers=env); assert o.status_code == 200, o.text
    j = o.json(); assert abs(j["duration"] - 10) < 0.3 and j["has_video"] and j["has_audio"] and j["width"] == 320
    got = client.get(j["url"], headers={"Range": "bytes=0-99"}); assert got.status_code == 206 and len(got.content) == 100       # seeking works
    assert client.get(j["url"].split("sig=")[0] + "sig=bad").status_code == 403                                                  # a made-up address is refused

def test_insert_a_clip_inside_a_video(client, env, media):
    """A 10 second video with a 2 second clip put in at the 4th second: 4 + 2 + 6 = 12 seconds."""
    g = upload(client, env, media / "main.webm"); rid = g["tracks"][0]["id"]
    a = client.post("/api/v1/podcasts/edit/assets", headers=env, data={"kind": "clip"}, files={"file": ("clip.mp4", (media / "clip.mp4").read_bytes(), "video/mp4")}); assert a.status_code == 200, a.text
    aid = a.json()["id"]; assert abs(a.json()["duration"] - 2) < 0.2
    body = {"title": "Inserted", "sources": {"a": {"kind": "rec", "id": rid}, "b": {"kind": "asset", "id": aid}},
            "segments": [{"source": "a", "start": 0, "end": 4}, {"source": "b", "start": 0, "end": 2}, {"source": "a", "start": 4, "end": 10}]}
    r = client.post("/api/v1/podcasts/edit/render", headers=env, json=body); assert r.status_code == 200, r.text
    j = wait(client, env, r.json()["job_id"]); assert j["status"] == "done", j
    t = dur(client, env, j["group_id"]); assert t["mimetype"] == "video/mp4" and t["has_video"]
    assert abs(j["duration"] - 12) < 0.2, j
    assert client.get(f"/api/v1/podcasts/{t['id']}/file", headers=env).content[4:8] == b"ftyp"
    orig = dur(client, env, g["group_id"]); assert orig["size_bytes"] == g["tracks"][0]["size_bytes"]                              # the original is untouched

def test_cut_join_smooth_and_voiceover(client, env, media):
    g1 = upload(client, env, media / "main.webm", "One"); g2 = upload(client, env, media / "main.webm", "Two")
    r1, r2 = g1["tracks"][0]["id"], g2["tracks"][0]["id"]
    vo = client.post("/api/v1/podcasts/edit/assets", headers=env, data={"kind": "voice"}, files={"file": ("vo.wav", (media / "vo.wav").read_bytes(), "audio/wav")}).json()
    body = {"sources": {"a": {"kind": "rec", "id": r1}, "b": {"kind": "rec", "id": r2}, "v": {"kind": "asset", "id": vo["id"]}},
            "segments": [{"source": "a", "start": 0, "end": 3}, {"source": "a", "start": 6, "end": 10}, {"source": "b", "start": 2, "end": 5}],   # cut 3-6 from the first, then join the second
            "crossfade": 0.5, "fade_in": 0.3, "fade_out": 0.3, "voiceovers": [{"source": "v", "at": 1, "gain": 1}], "original_volume": 0.3, "polish": True, "height": "480"}
    r = client.post("/api/v1/podcasts/edit/render", headers=env, json=body); assert r.status_code == 200, r.text
    j = wait(client, env, r.json()["job_id"]); assert j["status"] == "done", j
    assert abs(j["duration"] - (3 + 4 + 3 - 2 * 0.5)) < 0.25, j                      # 10 s of pieces, less the two overlaps
    t = dur(client, env, j["group_id"])
    assert t["height"] == 180                                                          # never scaled up past the source

def test_background_change_and_bad_requests(client, env, media):
    ff("-f", "lavfi", "-i", "color=c=0x00ff00:s=320x180:d=2:r=25,drawbox=x=100:y=20:w=100:h=150:color=red:t=fill", "-f", "lavfi", "-i", "sine=d=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(media / "green.mp4"))
    a = client.post("/api/v1/podcasts/edit/assets", headers=env, data={"kind": "clip"}, files={"file": ("g.mp4", (media / "green.mp4").read_bytes(), "video/mp4")}).json()
    r = client.post("/api/v1/podcasts/edit/render", headers=env, json={"sources": {"a": {"kind": "asset", "id": a["id"]}}, "segments": [{"source": "a", "start": 0, "end": 2}],
                                                                       "background": {"mode": "color", "color": "ff8800"}})
    j = wait(client, env, r.json()["job_id"]); assert j["status"] == "done", j
    # nonsense is refused with a clear message
    bad = client.post("/api/v1/podcasts/edit/render", headers=env, json={"sources": {"a": {"kind": "asset", "id": a["id"]}}, "segments": [{"source": "zz", "start": 0, "end": 1}]}); assert bad.status_code == 422
    over = client.post("/api/v1/podcasts/edit/render", headers=env, json={"sources": {"a": {"kind": "asset", "id": a["id"]}}, "segments": [{"source": "a", "start": 0, "end": 50}]})
    j = wait(client, env, over.json()["job_id"]); assert j["status"] == "error" and "past the end" in j["message"]
    nf = client.post("/api/v1/podcasts/edit/assets", headers=env, data={"kind": "clip"}, files={"file": ("x.exe", b"MZ" + b"0" * 100, "application/octet-stream")}); assert nf.status_code == 415

def test_editing_needs_the_cloud_and_other_peoples_clips_are_off_limits(client, env, media, monkeypatch):
    g = upload(client, env, media / "main.webm"); rid = g["tracks"][0]["id"]
    from app.services import entitlements as ent
    real = ent.limits
    async def basic(db, user): return {**(await real(db, user)), "cloud_podcast": False}
    monkeypatch.setattr(ent, "limits", basic)
    r = client.post(f"/api/v1/podcasts/edit/open/{rid}", headers=env); assert r.status_code == 403 and "cloud" in r.text
    assert client.post("/api/v1/podcasts/edit/render", headers=env, json={}).status_code == 403
    monkeypatch.setattr(ent, "limits", real)
    assert client.post("/api/v1/podcasts/edit/open/not-a-real-id", headers=env).status_code == 404

# ------------------------------------------------------------------ YouTube
class FakeGoogle:
    """Stands in for Google's sign-in, channel and upload servers."""
    def __init__(self): self.calls = []; self.uploaded = 0; self.meta = None; self.fail_once = False
    def handler(self, req: httpx.Request) -> httpx.Response:
        u = str(req.url); self.calls.append((req.method, u.split("?")[0]))
        if u.startswith("https://oauth2.googleapis.com/token"):
            f = parse_qs(req.content.decode())
            if f["client_secret"][0] == "wrong": return httpx.Response(401, json={"error": "invalid_client"})
            if f["grant_type"][0] == "authorization_code": return httpx.Response(200, json={"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600, "scope": "openid email https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"})
            return httpx.Response(200, json={"access_token": "at2", "expires_in": 3600})
        if "openidconnect" in u: return httpx.Response(200, json={"email": "Host@Example.com"})
        if "/youtube/v3/channels" in u: return httpx.Response(200, json={"items": [{"id": "UC123", "snippet": {"title": "My Podcast Channel"}}]})
        if "oauth2.googleapis.com/revoke" in u: return httpx.Response(200)
        if "upload/youtube/v3/videos" in u:
            assert req.headers["authorization"] == "Bearer at2"
            self.meta = json.loads(req.content); return httpx.Response(200, headers={"location": "https://upload.example/session1"})
        if u.startswith("https://upload.example/session1"):
            if req.headers.get("content-range", "").startswith("bytes */"): return httpx.Response(308, headers={"range": "bytes=0-%d" % (self.uploaded - 1)} if self.uploaded else {})
            if self.fail_once: self.fail_once = False; return httpx.Response(503)
            start, end, total = [int(x) for x in req.headers["content-range"].replace("bytes ", "").replace("/", "-").split("-")]
            assert start == self.uploaded; self.uploaded = end + 1
            return httpx.Response(200, json={"id": "vid123"}) if self.uploaded >= total else httpx.Response(308, headers={"range": f"bytes=0-{end}"})
        return httpx.Response(404)

@pytest.fixture()
def google(monkeypatch):
    from app.services import youtube as yt
    g = FakeGoogle(); monkeypatch.setattr(yt, "http", lambda timeout=60: httpx.AsyncClient(transport=httpx.MockTransport(g.handler), timeout=timeout))
    monkeypatch.setattr(yt, "CHUNK", 64 * 1024); yt._CACHE.clear(); return g

CID = "1234567890-abc.apps.googleusercontent.com"

def connect(client, h, google):
    assert client.put("/api/v1/podcasts/youtube/credentials", headers=h, json={"client_id": CID, "client_secret": "s3cret"}).status_code == 200
    c = client.post("/api/v1/podcasts/youtube/connect", headers=h, json={"origin": "https://app.isift.au"}); assert c.status_code == 200, c.text
    q = parse_qs(urlsplit(c.json()["url"]).query)
    assert q["client_id"] == [CID] and "youtube.upload" in q["scope"][0] and q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    assert c.json()["redirect_uri"] == "https://app.isift.au/api/v1/podcasts/youtube/callback"
    return q["state"][0]

def test_youtube_credentials_and_sign_in(client, env, google):
    s = client.get("/api/v1/podcasts/youtube", headers=env, params={"origin": "https://app.isift.au"}).json()
    assert s["connected"] is False and s["has_secret"] is False and s["redirect_uri"].endswith("/api/v1/podcasts/youtube/callback")
    assert client.put("/api/v1/podcasts/youtube/credentials", headers=env, json={"client_id": "nope", "client_secret": "x"}).status_code == 422
    assert client.put("/api/v1/podcasts/youtube/credentials", headers=env, json={"client_id": CID}).status_code == 422                 # the secret is needed too
    assert client.post("/api/v1/podcasts/youtube/connect", headers=env, json={"origin": "https://app.isift.au"}).status_code == 409    # nothing saved yet
    state = connect(client, env, google)
    ok = client.get("/api/v1/podcasts/youtube/callback", params={"code": "abc", "state": state}); assert ok.status_code == 200 and "YouTube connected" in ok.text
    s = client.get("/api/v1/podcasts/youtube", headers=env).json()
    assert s["connected"] is True and s["channel"] == "My Podcast Channel" and s["email"] == "host@example.com" and s["has_secret"] is True and s["client_id"] == CID
    assert "s3cret" not in json.dumps(s) and "rt1" not in json.dumps(s)                                                                 # secrets never go back to the browser
    assert "expired" in client.get("/api/v1/podcasts/youtube/callback", params={"code": "abc", "state": state}).text                    # a sign-in link works once
    assert client.delete("/api/v1/podcasts/youtube", headers=env).json()["ok"] is True
    assert client.get("/api/v1/podcasts/youtube", headers=env).json()["connected"] is False
    assert ("POST", "https://oauth2.googleapis.com/revoke") in google.calls

def test_youtube_wrong_secret_is_explained(client, env, google):
    client.put("/api/v1/podcasts/youtube/credentials", headers=env, json={"client_id": CID, "client_secret": "wrong"})
    state = parse_qs(urlsplit(client.post("/api/v1/podcasts/youtube/connect", headers=env, json={"origin": "https://x.test"}).json()["url"]).query)["state"][0]
    page = client.get("/api/v1/podcasts/youtube/callback", params={"code": "abc", "state": state}); assert "not connected" in page.text and "Client ID and secret" in page.text

def test_one_click_post_to_youtube(client, env, media, google):
    g = upload(client, env, media / "main.webm", "Episode 1")
    assert client.post(f"/api/v1/podcasts/{g['group_id']}/youtube", headers=env, json={}).status_code == 409                          # not connected yet
    state = connect(client, env, google); client.get("/api/v1/podcasts/youtube/callback", params={"code": "abc", "state": state})
    google.fail_once = True                                                                                                             # one hiccup mid-upload: it resumes
    r = client.post(f"/api/v1/podcasts/{g['group_id']}/youtube", headers=env, json={"description": "Hello <b>world</b>", "tags": ["pod", "talk"]}); assert r.status_code == 200, r.text
    j = wait(client, env, r.json()["job_id"]); assert j["status"] == "done", j
    assert j["url"] == "https://www.youtube.com/watch?v=vid123" and "private" in j["message"]
    assert google.meta["snippet"]["title"] == "Episode 1" and google.meta["status"]["privacyStatus"] == "private" and "<" not in google.meta["snippet"]["description"]
    assert google.meta["snippet"]["tags"] == ["pod", "talk"]
    assert google.uploaded > 64 * 1024                                                                                                  # went up in more than one piece
    assert client.get(f"/api/v1/podcasts/jobs/{j['id']}", headers={"Authorization": "Bearer nope"}).status_code in (401, 403)
    pub = client.post(f"/api/v1/podcasts/{g['group_id']}/youtube", headers=env, json={"privacy": "unlisted"}).json()["job_id"]
    google.uploaded = 0; assert wait(client, env, pub)["status"] == "done" and google.meta["status"]["privacyStatus"] == "unlisted"

def test_sound_only_podcast_gets_a_picture_for_youtube(client, env, media, google):
    g = upload(client, env, media / "talk.webm", "Audio show", video=False)
    state = connect(client, env, google); client.get("/api/v1/podcasts/youtube/callback", params={"code": "abc", "state": state})
    j = wait(client, env, client.post(f"/api/v1/podcasts/{g['group_id']}/youtube", headers=env, json={}).json()["job_id"]); assert j["status"] == "done", j

# ------------------------------------------------------------------ paid plans only
def test_editor_and_youtube_are_paid_plan_features(client, env, media, monkeypatch):
    from app.services import entitlements as ent
    assert ent.plan_defaults("basic")["podcast_edit"] is False and ent.plan_defaults("basic")["youtube_post"] is False
    for paid in ("individual", "business"):
        d = ent.plan_defaults(paid); assert d["podcast_edit"] is True and d["youtube_post"] is True
    assert "podcast_edit" in ent.FIELDS and "youtube_post" in ent.FIELDS                                  # the administrator can change both, per plan or per person
    g = upload(client, env, media / "main.webm"); rid = g["tracks"][0]["id"]
    assert client.get("/api/v1/podcasts/config", headers=env).json()["edit_allowed"] is True
    real = ent.limits
    async def basic(db, user): return {**(await real(db, user)), **{k: v for k, v in ent.plan_defaults("basic").items() if k in ("podcast_edit", "youtube_post", "cloud_podcast")}}
    monkeypatch.setattr(ent, "limits", basic)
    c = client.get("/api/v1/podcasts/config", headers=env).json(); assert c["edit_allowed"] is False and c["youtube_allowed"] is False
    e = client.post(f"/api/v1/podcasts/edit/open/{rid}", headers=env); assert e.status_code == 403 and "paid plans" in e.text
    y = client.post(f"/api/v1/podcasts/{g['group_id']}/youtube", headers=env, json={}); assert y.status_code == 403 and "paid plans" in y.text
    async def edit_only(db, user): return {**(await real(db, user)), "youtube_post": False}                # one switch off does not turn the other off
    monkeypatch.setattr(ent, "limits", edit_only)
    assert client.post(f"/api/v1/podcasts/edit/open/{rid}", headers=env).status_code == 200
    assert client.post(f"/api/v1/podcasts/{g['group_id']}/youtube", headers=env, json={}).status_code == 403
