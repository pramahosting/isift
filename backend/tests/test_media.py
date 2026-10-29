import asyncio, io, subprocess, time
import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PUSH_LOOP", "false")
    from app.main import app
    from app.core.db import engine
    from app.models import Base
    async def mk():
        async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    asyncio.run(mk())
    with TestClient(app) as c:
        yield c


def login(c):
    r = c.post("/api/v1/auth/local-login", json={"username": "admin", "password": "Meeting$1"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_images(client):
    from PIL import Image
    c = client; h = login(c)
    buf = io.BytesIO(); Image.new("RGBA", (40, 30), (255, 0, 0, 128)).save(buf, "PNG")
    for to, magic in (("jpg", b"\xff\xd8"), ("gif", b"GIF8"), ("webp", b"RIFF"), ("bmp", b"BM"), ("pdf", b"%PDF"), ("tiff", None)):
        r = c.post(f"/api/v1/media/image?filename=pic.png&to={to}", content=buf.getvalue(), headers=h); assert r.status_code == 200, (to, r.text)
        assert magic is None or r.content.startswith(magic); assert r.headers["x-filename"] == f"pic.{to}"
    assert c.post("/api/v1/media/image?filename=a.txt&to=jpg", content=b"nope", headers=h).status_code == 422
    assert c.post("/api/v1/media/image?filename=a.png&to=exe", content=buf.getvalue(), headers=h).status_code == 422


def test_video_needs_blob_storage_and_is_stored_there(client, monkeypatch, tmp_path):
    from app.services import storage
    c = client; h = login(c)
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-shortest", str(clip)], capture_output=True, check=True)
    r = c.post("/api/v1/media/video?filename=c.mp4&to=mov", content=clip.read_bytes(), headers=h); assert r.status_code == 409 and "blob storage" in r.json()["detail"]
    blobs = {}
    monkeypatch.setattr(storage, "configured", lambda: True)
    monkeypatch.setattr(storage, "_put", lambda path, key, mime: blobs.__setitem__(key, open(path, "rb").read()))
    monkeypatch.setattr(storage, "delete_object", lambda key: bool(blobs.pop(key, None)))
    monkeypatch.setattr(storage, "presigned_url", lambda key, name, mime, seconds=900: "https://r2.example/" + key)
    r = c.post("/api/v1/media/video?filename=My clip.mp4&to=mov", content=clip.read_bytes(), headers={**h, "Content-Type": "video/mp4"}); assert r.status_code == 200, r.text
    jid = r.json()["id"]
    for _ in range(60):
        j = [x for x in c.get("/api/v1/media/jobs", headers=h).json()["items"] if x["id"] == jid][0]
        if j["state"] in ("done", "error"): break
        time.sleep(0.5)
    assert j["state"] == "done", j
    assert j["out_name"] == "My clip.mov" and len(blobs) == 2 and any(k.endswith("-original.mp4") for k in blobs) and any(k.endswith(".mov") for k in blobs)
    out = next(v for k, v in blobs.items() if k.endswith(".mov")); assert out[4:8] == b"ftyp" and b"qt" in out[:16]          # a real QuickTime file
    u = c.get(f"/api/v1/media/{jid}/url", headers=h).json(); assert u["url"].startswith("https://r2.example/") and u["name"] == "My clip.mov"
    assert c.delete(f"/api/v1/media/{jid}", headers=h).status_code == 200 and not blobs
    assert c.get(f"/api/v1/media/{jid}/url", headers=h).status_code == 404


def test_compress_to_hevc_and_av1(client, monkeypatch, tmp_path):
    import subprocess, time
    from app.services import storage
    c = client; h = login(c)
    clip = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15", "-t", "2", "-pix_fmt", "yuv420p", str(clip)], capture_output=True, check=True)
    blobs = {}
    monkeypatch.setattr(storage, "configured", lambda: True)
    monkeypatch.setattr(storage, "_put", lambda path, key, mime: blobs.__setitem__(key, open(path, "rb").read()))
    monkeypatch.setattr(storage, "delete_object", lambda key: bool(blobs.pop(key, None)))
    for to, name in (("hevc", "hvc1"), ("av1", "av01")):
        blobs.clear()
        r = c.post(f"/api/v1/media/video?filename=c.mp4&to={to}&quality=small", content=clip.read_bytes(), headers=h); assert r.status_code == 200, r.text
        for _ in range(120):
            j = [x for x in c.get("/api/v1/media/jobs", headers=h).json()["items"] if x["id"] == r.json()["id"]][0]
            if j["state"] in ("done", "error"): break
            time.sleep(0.5)
        assert j["state"] == "done", j
        assert j["out_name"] == "c-compressed.mp4"
        out = next(v for k, v in blobs.items() if k.endswith("-compressed.mp4")); assert out[4:8] == b"ftyp" and name.encode() in out


def test_modules_switch_off_converters(client):
    c = client; h = login(c)
    ids = [m["id"] for m in c.get("/api/v1/modules").json()["modules"]]
    assert {"docconverter", "mediaconverter", "signpdf"} <= set(ids)
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (8, 8)).save(buf, "PNG")
    assert c.post("/api/v1/media/image?filename=a.png&to=jpg", content=buf.getvalue(), headers=h).status_code == 200
    on = {i: True for i in ids}; on["mediaconverter"] = False; on["signpdf"] = False; on["docconverter"] = False
    assert c.put("/api/v1/admin/modules", json={"enabled": on}, headers=h).status_code == 200
    assert c.post("/api/v1/media/image?filename=a.png&to=jpg", content=buf.getvalue(), headers=h).status_code == 403
    assert c.post("/api/v1/docs/file-to-pdf", json={"name": "a.docx", "data": ""}, headers=h).status_code == 403
    assert c.post("/api/v1/docedit/inspect", json={}, headers=h).status_code == 403
    on = {i: True for i in ids}; c.put("/api/v1/admin/modules", json={"enabled": on}, headers=h)
    assert c.post("/api/v1/media/image?filename=a.png&to=jpg", content=buf.getvalue(), headers=h).status_code == 200
