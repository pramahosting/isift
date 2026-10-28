import asyncio
import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def client():
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
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_marketing_files(client):
    c = client; h = login(c)
    assert c.get("/api/v1/admin/marketing").status_code in (401, 403)
    assert c.get("/api/v1/marketing/landing").json() == {"video": None, "playbook": None}
    vid = bytes(range(256)) * 40
    r = c.post("/api/v1/admin/marketing?filename=promo.mp4&title=Promo", content=vid, headers={**h, "Content-Type": "video/mp4"}); assert r.status_code == 200, r.text
    v = r.json(); assert v["kind"] == "video" and v["size_bytes"] == len(vid) and v["storage"] == "database"
    pb = c.post("/api/v1/admin/marketing?filename=Playbook.pdf", content=b"%PDF-1.4 x", headers={**h, "Content-Type": "application/pdf"}).json(); assert pb["kind"] == "document"
    assert pb["landing"] and pb["title"] == "isift-playbook" and pb["filename"] == "isift-playbook.pdf" and v["landing"] and v["title"] == "isift-video" and v["filename"] == "isift-video.mp4"   # first ones take the landing slots, renamed
    land = c.get("/api/v1/marketing/landing").json(); assert land["video"]["id"] == v["id"] and land["playbook"]["id"] == pb["id"]
    ot = c.post("/api/v1/admin/marketing?filename=other.png", content=b"x", headers={**h, "Content-Type": "image/png"}).json()
    assert c.patch(f"/api/v1/admin/marketing/{ot['id']}", json={"landing": True}, headers=h).status_code == 400
    p = c.patch(f"/api/v1/admin/marketing/{v['id']}", json={"landing": True}, headers=h).json(); assert p["landing"] and p["public"]
    assert c.get(f"/api/v1/marketing/{v['id']}/file").content == vid
    rg = c.get(f"/api/v1/marketing/{v['id']}/file", headers={"Range": "bytes=10-19"}); assert rg.status_code == 206 and rg.content == vid[10:20] and rg.headers["content-range"] == f"bytes 10-19/{len(vid)}"
    assert c.get(f"/api/v1/marketing/{v['id']}/file", headers={"Range": "bytes=-5"}).content == vid[-5:]
    assert c.get(f"/api/v1/admin/marketing/{pb['id']}/file", headers=h).content == b"%PDF-1.4 x"
    new = b"x" * 500
    r = c.put(f"/api/v1/admin/marketing/{v['id']}/file?filename=promo2.mp4", content=new, headers={**h, "Content-Type": "video/mp4"}).json(); assert r["size_bytes"] == 500 and r["filename"] == "isift-video.mp4" and r["title"] == "isift-video"
    assert c.get(f"/api/v1/marketing/{v['id']}/file").content == new
    assert c.patch(f"/api/v1/admin/marketing/{v['id']}", json={"public": False}, headers=h).json()["landing"] is False
    assert c.get("/api/v1/marketing/landing").json()["video"] is None
    assert len(c.get("/api/v1/admin/marketing", headers=h).json()["items"]) == 3
    assert c.delete(f"/api/v1/admin/marketing/{v['id']}", headers=h).status_code == 200 and c.delete(f"/api/v1/admin/marketing/{v['id']}", headers=h).status_code == 404
