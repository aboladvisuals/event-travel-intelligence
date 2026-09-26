from datetime import datetime, timedelta, timezone

from backend.live_transport import (
    apply_live_traffic,
    attach_live_to_journey,
    configured_disruptions,
    fetch_tomtom_live_delay,
    get_live_transport,
    is_stale,
    live_traffic_available,
    live_traffic_unavailable,
    structured_disruption,
    clear_live_cache,
)
from backend.travel_engine import calculate_journey, format_arrival, journey_breakdown


def test_unavailable_live_does_not_change_estimate():
    breakdown = journey_breakdown(123, 148, 0)
    live = live_traffic_unavailable("No licensed live speed feed is configured.")
    result = apply_live_traffic(breakdown, live)
    assert result["live_traffic_available"] is False
    assert result["live_traffic_minutes"] is None
    assert result["normal_minutes"] == 123
    assert result["event_impact_minutes"] == 25
    assert result["estimated_minutes"] == 148


def test_available_live_adds_separately_and_keeps_osrm_normal():
    breakdown = journey_breakdown(123, 148, 0)
    live = live_traffic_available(18, source="TomTom Routing")
    result = apply_live_traffic(breakdown, live)
    assert result["normal_minutes"] == 123
    assert result["live_traffic_minutes"] == 18
    assert result["event_impact_minutes"] == 25
    assert result["extra_delay_minutes"] == 0
    assert result["estimated_minutes"] == 166
    assert result["live_traffic_available"] is True


def test_stale_live_is_not_applied_to_estimate():
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    live = live_traffic_available(18, source="TomTom Routing", checked_at=old)
    assert live["status"] == "stale"
    assert live["available"] is False
    assert live["additional_minutes"] is None
    breakdown = apply_live_traffic(journey_breakdown(123, 148, 0), live)
    assert breakdown["live_traffic_available"] is False
    assert breakdown["estimated_minutes"] == 148


def test_normal_journey_still_has_zero_event_impact():
    result = calculate_journey(
        normal_minutes=123,
        departure_time=datetime.strptime("08:00", "%H:%M"),
        direction="outbound",
        event={
            "traffic_management_start": "11:30",
            "traffic_management_end": "21:00",
            "start_time": "11:30",
        },
    )
    updated = attach_live_to_journey(
        result,
        live_traffic_unavailable("Live speed data is unavailable."),
        format_arrival=format_arrival,
    )
    assert updated["breakdown"]["event_impact_minutes"] == 0
    assert updated["estimated_minutes"] == 123
    assert updated["arrival_time"] == "10:03"


def test_event_journey_keeps_event_model_when_live_missing():
    result = calculate_journey(
        normal_minutes=100,
        departure_time=datetime.strptime("15:00", "%H:%M"),
        direction="outbound",
        event={
            "traffic_management_start": "11:30",
            "traffic_management_end": "21:00",
        },
    )
    updated = attach_live_to_journey(
        result,
        live_traffic_unavailable("Live speed data is unavailable."),
        format_arrival=format_arrival,
    )
    assert updated["label"] == "Main event period"
    assert updated["breakdown"]["event_impact_minutes"] == 35
    assert updated["estimated_minutes"] == 135
    assert updated["breakdown"]["live_traffic_minutes"] is None


def test_api_failure_does_not_fabricate_live_minutes():
    import os

    class Boom:
        def raise_for_status(self):
            raise RuntimeError("API failure")

        def json(self):
            return {}

    previous = os.environ.get("TOMTOM_API_KEY")
    os.environ["TOMTOM_API_KEY"] = "test-key-not-secret"
    try:
        live = fetch_tomtom_live_delay(
            {"latitude": 53.74, "longitude": -0.33},
            {"latitude": 53.46, "longitude": -2.29},
            fetcher=lambda url, params=None: Boom(),
        )
    finally:
        if previous is None:
            os.environ.pop("TOMTOM_API_KEY", None)
        else:
            os.environ["TOMTOM_API_KEY"] = previous
    assert live["available"] is False
    assert live["additional_minutes"] is None
    assert "failed" in live["note"].lower()


def test_configured_disruptions_are_not_labelled_live():
    event = {
        "verified_disruptions": [
            {
                "title": "M60 Simister Island closure",
                "type": "Road closure",
                "start": "2026-09-26",
                "end": "2026-09-28",
                "impact": "M60 J17-J18 closure",
                "source": "TfGM",
            }
        ]
    }
    records = configured_disruptions(event, checked_at="2026-09-26T08:00:00Z")
    assert records[0]["origin"] == "configured"
    assert records[0]["status"] == "configured"
    assert records[0]["title"] == "M60 Simister Island closure"
    assert records[0]["source"] == "TfGM"
    assert records[0]["checked_at"] == "2026-09-26T08:00:00Z"


def test_structured_live_record_shape():
    record = structured_disruption(
        title="M6 lane closure",
        disruption_type="Lane closure",
        affected_road="M6",
        location="J19-J20 northbound",
        start="2026-09-26T07:00:00Z",
        end="2026-09-26T12:00:00Z",
        severity="moderate",
        status="active",
        source="National Highways",
        origin="live",
        checked_at="2026-09-26T08:10:00Z",
    )
    for field in (
        "title",
        "type",
        "affected_road",
        "location",
        "start",
        "end",
        "severity",
        "status",
        "source",
        "checked_at",
    ):
        assert field in record
    assert record["origin"] == "live"


def test_stale_helper():
    now = datetime(2026, 9, 26, 8, 30, tzinfo=timezone.utc)
    fresh = "2026-09-26T08:20:00Z"
    old = "2026-09-26T08:00:00Z"
    assert is_stale(fresh, now=now) is False
    assert is_stale(old, now=now) is True


def test_get_live_transport_without_keys_reports_unavailable():
    clear_live_cache()
    from backend import live_transport as module

    original_webtris = module.check_webtris
    original_tfgm = module.check_tfgm_status
    original_live_delay = module.fetch_tomtom_live_delay
    original_live_disruption = module.fetch_live_disruptions
    try:
        module.check_webtris = lambda fetcher=None: {
            "available": True,
            "status": "available",
            "source": "National Highways WebTRIS",
            "checked_at": "2026-09-26T08:00:00Z",
            "age_minutes": 0,
            "note": "reachable",
        }
        module.check_tfgm_status = lambda fetcher=None: {
            "available": False,
            "status": "unavailable",
            "source": "TfGM",
            "checked_at": "2026-09-26T08:00:00Z",
            "age_minutes": 0,
            "note": "down",
        }
        module.fetch_tomtom_live_delay = lambda *args, **kwargs: live_traffic_unavailable(
            "No licensed live speed feed is configured."
        )
        module.fetch_live_disruptions = lambda fetcher=None: {
            "available": False,
            "status": "unavailable",
            "items": [],
            "source": "None configured",
            "checked_at": "2026-09-26T08:00:00Z",
            "age_minutes": 0,
            "note": "no key",
        }
        payload = get_live_transport(
            event={"verified_disruptions": [{"title": "Event traffic", "type": "Event traffic", "start": "11:30", "end": "21:00", "impact": "congestion", "source": "TfGM"}]}
        )
    finally:
        module.check_webtris = original_webtris
        module.check_tfgm_status = original_tfgm
        module.fetch_tomtom_live_delay = original_live_delay
        module.fetch_live_disruptions = original_live_disruption
        clear_live_cache()

    assert payload["live_traffic"]["available"] is False
    assert payload["live_traffic"]["additional_minutes"] is None
    assert payload["configured_disruptions"][0]["origin"] == "configured"
    assert payload["live_disruptions"]["items"] == []


if __name__ == "__main__":
    tests = [
        test_unavailable_live_does_not_change_estimate,
        test_available_live_adds_separately_and_keeps_osrm_normal,
        test_stale_live_is_not_applied_to_estimate,
        test_normal_journey_still_has_zero_event_impact,
        test_event_journey_keeps_event_model_when_live_missing,
        test_api_failure_does_not_fabricate_live_minutes,
        test_configured_disruptions_are_not_labelled_live,
        test_structured_live_record_shape,
        test_stale_helper,
        test_get_live_transport_without_keys_reports_unavailable,
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
    print(len(tests), "live transport tests passed")
