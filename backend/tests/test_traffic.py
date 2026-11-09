"""Tagged-link traffic: visits are counted once a day, sign-ups are matched to the first link, and only admins see it."""
from tests.test_room_access import client, login   # noqa: F401  (fixtures)

TAG = {"source": "linkedin", "medium": "social", "campaign": "posts", "content": "day3", "vid": "abc123"}

def test_visits_and_signups_by_link(client):
    ah, _ = login(client)
    assert client.get("/api/v1/admin/traffic", headers=ah).json()["total_visits"] == 0
    assert client.post("/api/v1/track/visit", json=TAG).status_code == 200
    client.post("/api/v1/track/visit", json=TAG)                                   # same browser, same day: not counted again
    client.post("/api/v1/track/visit", json={**TAG, "vid": "other", "content": "day1"})
    client.post("/api/v1/track/visit", json={})                                    # no tag: ignored
    assert client.post("/api/v1/track/attribute", json=TAG, headers=ah).status_code == 200
    client.post("/api/v1/track/attribute", json={**TAG, "content": "day9"}, headers=ah)   # first link wins
    j = client.get("/api/v1/admin/traffic", headers=ah).json()
    assert j["total_visits"] == 2 and j["total_signups"] == 1
    by = {r["content"]: r for r in j["rows"]}
    assert by["day3"]["visits"] == 1 and by["day3"]["signups"] == 1 and by["day3"]["rate"] == 100.0
    assert by["day1"]["visits"] == 1 and by["day1"]["signups"] == 0
    assert "day9" not in by

def test_traffic_is_admin_only(client):
    assert client.get("/api/v1/admin/traffic").status_code in (401, 403)
    assert client.post("/api/v1/track/attribute", json=TAG).status_code in (401, 403)
