import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_PATH", str(Path(tempfile.gettempdir()) / "eti-api-test.sqlite"))

from fastapi.testclient import TestClient

from backend.main import app
from backend.rate_limit import reset as reset_limits


def test_health_and_ready():
    reset_limits()
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["version"].startswith("1.6")
    assert body["status"] in {"healthy", "degraded"}
    assert "database" in body
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_event_discovery_endpoints():
    reset_limits()
    client = TestClient(app)
    events = client.get("/events")
    assert events.status_code == 200
    ids = [item["event_id"] for item in events.json()]
    assert "nsppd-uk-old-trafford-2026" in ids
    search = client.get("/events/search", params={"q": "Old Trafford"})
    assert search.status_code == 200
    assert search.json()[0]["venue"] == "Old Trafford"
    missing = client.get("/events/not-a-real-event")
    assert missing.status_code == 404


def test_live_endpoints_degrade_without_keys():
    reset_limits()
    client = TestClient(app)
    transport = client.get("/transport/live")
    assert transport.status_code == 200
    payload = transport.json()
    assert "live_traffic" in payload
    parking = client.get("/parking/live")
    assert parking.status_code == 200
    assert parking.json()["feed"]["available"] in {False, True}


def test_analyze_rejects_bad_input():
    reset_limits()
    client = TestClient(app)
    empty = client.post("/analyze", json={
        "start_location": "",
        "departure_time": "08:00",
        "return_time": "20:30",
    })
    assert empty.status_code in {400, 422}
    bad_time = client.post("/analyze", json={
        "start_location": "Hull",
        "departure_time": "morning",
        "return_time": "20:30",
    })
    assert bad_time.status_code == 422
    unknown = client.post("/analyze", json={
        "start_location": "Hull",
        "departure_time": "08:00",
        "return_time": "20:30",
        "event_id": "does-not-exist",
    })
    assert unknown.status_code == 404


def test_health_does_not_leak_secrets():
    reset_limits()
    client = TestClient(app)
    body = client.get("/health").json()
    text = str(body)
    assert "TOMTOM_API_KEY" not in text
    assert os.getenv("TOMTOM_API_KEY", "sentinel") not in text or not os.getenv("TOMTOM_API_KEY")


if __name__ == "__main__":
    tests = [
        test_health_and_ready,
        test_event_discovery_endpoints,
        test_live_endpoints_degrade_without_keys,
        test_analyze_rejects_bad_input,
        test_health_does_not_leak_secrets,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print("PASS", test.__name__)
        except Exception as error:
            failed += 1
            print("FAIL", test.__name__, error)
    if failed:
        raise SystemExit(1)
    print(len(tests), "api tests passed")
