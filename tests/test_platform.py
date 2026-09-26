import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_PATH", str(Path(tempfile.gettempdir()) / "eti-platform-test.sqlite"))

from backend.cache import cache_clear, cache_get, cache_set
from backend.db import event_count, ping, reset_connection, sync_events
from backend.event_store import list_events
from backend.rate_limit import allow, reset as reset_limits
from backend.settings import APP_VERSION, analyze_rate_limit
from backend.travel_engine import calculate_crowd_risk, calculate_journey
from datetime import datetime


def test_version_is_platform_release():
    assert APP_VERSION.startswith("1.6")


def test_database_syncs_events_disruptions_and_parking():
    reset_connection()
    assert ping() is True
    sync_events(list_events())
    assert event_count() == 2


def test_cache_round_trip_and_stale_fallback():
    cache_clear("platform-test")
    cache_set("platform-test", "hull", {"lat": 53.7}, ttl_seconds=60)
    payload, stale = cache_get("platform-test", "hull")
    assert payload["lat"] == 53.7
    assert stale is False
    cache_set("platform-test", "old", {"ok": True}, ttl_seconds=-10)
    missing, _ = cache_get("platform-test", "old")
    assert missing is None
    stale_payload, was_stale = cache_get("platform-test", "old", allow_stale=True)
    assert stale_payload["ok"] is True
    assert was_stale is True


def test_rate_limiter_allows_then_blocks():
    reset_limits()
    for _ in range(3):
        ok, retry, used = allow("test-bucket", 3, 60)
        assert ok is True
        assert retry == 0
        assert used >= 1
    ok, retry, used = allow("test-bucket", 3, 60)
    assert ok is False
    assert retry >= 1
    assert used >= 3


def test_analyze_rate_limit_is_usable():
    assert analyze_rate_limit() >= 10


def test_journey_and_risk_still_work():
    event = {
        "traffic_management_start": "11:30",
        "traffic_management_end": "21:00",
        "start_time": "11:30",
        "capacity": 50000,
    }
    outbound = calculate_journey(100, datetime.strptime("08:00", "%H:%M"), "outbound", event)
    assert outbound["estimated_minutes"] == 100
    late = calculate_journey(100, datetime.strptime("20:30", "%H:%M"), "return", event)
    assert late["day_rollover"] is True
    crowd = calculate_crowd_risk(50000, datetime.strptime("12:00", "%H:%M"), event)
    assert crowd["level"] == "VERY HIGH"


if __name__ == "__main__":
    tests = [
        test_version_is_platform_release,
        test_database_syncs_events_disruptions_and_parking,
        test_cache_round_trip_and_stale_fallback,
        test_rate_limiter_allows_then_blocks,
        test_analyze_rate_limit_is_usable,
        test_journey_and_risk_still_work,
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
    print(len(tests), "platform tests passed")
