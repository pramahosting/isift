"""HD podcast recording: every plan may record; Basic always keeps it on its own computer, paid plans may also use the cloud."""
from tests.test_room_access import client, login, signed_up   # noqa: F401  (fixtures)
from tests.test_entitlements import basic_user, user_id

WEBM = bytes.fromhex("1A45DFA3") + b"x" * 4000
WAV = b"RIFF" + (4000).to_bytes(4, "little") + b"WAVE" + b"x" * 4000

def test_basic_is_local_only_and_cannot_upload(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    cfg = client.get("/api/v1/podcasts/config", headers=bh); assert cfg.status_code == 200, cfg.text
    c = cfg.json(); assert c["allowed"] is True and c["cloud_allowed"] is False and c["default_destination"] == "local" and "Upgrade" in c["cloud_note"]
    assert c["quality"]["audio_sample_rate"] == 48000 and c["quality"]["audio_kbps"] >= 256 and c["quality"]["video_ideal"]["height"] == 2160
    up = client.post("/api/v1/podcasts", headers=bh, data={"title": "Pilot"}, files={"master": ("m.webm", WEBM, "audio/webm")})
    assert up.status_code == 403 and "own computer" in up.text

def test_admin_can_give_one_basic_person_the_cloud(client, monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import storage
    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    client.get("/api/v1/podcasts/config", headers=bh)            # the person's record is made on their first request
    uid = user_id(client, ah, client.email)
    assert client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"cloud_podcast": True}}, headers=ah).status_code == 200
    up = client.post("/api/v1/podcasts", headers=bh, data={"title": "Ep 1", "duration_s": "62", "width": "1920", "height": "1080", "audio_kbps": "256", "track_labels": ["Host mic", "Guest mic"]},
                     files=[("master", ("m.webm", WEBM, "video/webm")), ("tracks", ("a.wav", WAV, "audio/wav")), ("tracks", ("b.webm", WEBM, "audio/webm"))])
    assert up.status_code == 200 and up.json()["tracks"] == 3, up.text
    lst = client.get("/api/v1/podcasts", headers=bh).json()
    assert len(lst) == 1 and lst[0]["title"] == "Ep 1" and [t["label"] for t in lst[0]["tracks"]] == ["Master", "Guest mic", "Host mic"] or lst[0]["tracks"][0]["is_master"]
    master = lst[0]["tracks"][0]; assert master["has_video"] and master["height"] == 1080
    wav = next(t for t in lst[0]["tracks"] if t["mimetype"] == "audio/wav")
    got = client.get(f"/api/v1/podcasts/{master['id']}/file", headers=bh); assert got.status_code == 200 and got.content == WEBM        # original quality: not re-encoded
    assert client.get(f"/api/v1/podcasts/{wav['id']}/file", headers=bh).content == WAV
    assert client.get(f"/api/v1/podcasts/{master['id']}/file", headers=ah).status_code == 404            # someone else's file is not theirs to read
    assert client.delete(f"/api/v1/podcasts/{lst[0]['group_id']}", headers=bh).json()["ok"] is True
    assert client.get("/api/v1/podcasts", headers=bh).json() == []

def test_paid_plan_gets_cloud_by_default_and_files_are_checked(client, monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))
    ah, _ = login(client)
    assert client.get("/api/v1/podcasts/config", headers=ah).json()["cloud_allowed"] is True       # the administrator is never limited
    bad = client.post("/api/v1/podcasts", headers=ah, data={"title": "x"}, files={"master": ("m.webm", b"not a recording at all", "audio/webm")})
    assert bad.status_code == 415
    assert client.post("/api/v1/podcasts", headers=ah, data={"title": "ok"}, files={"master": ("m.webm", WEBM, "audio/webm")}).status_code == 200

def test_switching_the_module_off_hides_the_studio(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    mods = client.get("/api/v1/modules", headers=ah).json()
    assert any(m["id"] == "podcast" for m in (mods["modules"] if isinstance(mods, dict) else mods))
