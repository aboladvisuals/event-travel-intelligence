from datetime import datetime

from backend.event_store import (
    DEFAULT_EVENT_ID,
    event_to_public,
    get_event,
    list_events,
)
from backend.travel_engine import (
    calculate_crowd_risk,
    calculate_journey,
    format_arrival,
    get_outbound_scenario,
    get_return_scenario,
)


def test_event_store_contains_production_and_test_events():
    events = {event.event_id: event for event in list_events()}
    assert DEFAULT_EVENT_ID in events
    assert "test-event-manchester" in events
    assert events[DEFAULT_EVENT_ID].name == "NSPPD UK Prayer Conference"
    assert events["test-event-manchester"].fictional is True
    assert events["test-event-manchester"].traffic_management_start == "14:00"


def test_alias_resolves_to_nsppd():
    event = get_event("nspdp-uk-old-trafford-2026")
    assert event.event_id == "nsppd-uk-old-trafford-2026"


def test_engine_uses_selected_event_windows():
    nsppd = event_to_public(get_event(DEFAULT_EVENT_ID))
    test_event = event_to_public(get_event("test-event-manchester"))
    ten = datetime.strptime("10:00", "%H:%M")
    fifteen = datetime.strptime("15:00", "%H:%M")

    assert get_outbound_scenario(ten, nsppd)["label"] == "Event build-up"
    assert get_outbound_scenario(ten, test_event)["label"] == "Normal / early departure"
    assert get_outbound_scenario(fifteen, nsppd)["label"] == "Main event period"
    assert get_outbound_scenario(fifteen, test_event)["label"] == "Main event period"


def test_return_window_follows_event_traffic_end():
    nsppd = event_to_public(get_event(DEFAULT_EVENT_ID))
    test_event = event_to_public(get_event("test-event-manchester"))
    half_seven = datetime.strptime("19:30", "%H:%M")

    assert get_return_scenario(half_seven, nsppd)["label"] == "Event still active"
    assert get_return_scenario(half_seven, test_event)["label"] == "Traffic beginning to ease"


def test_crowd_risk_uses_event_capacity_and_window():
    nsppd = event_to_public(get_event(DEFAULT_EVENT_ID))
    test_event = event_to_public(get_event("test-event-manchester"))
    afternoon = datetime.strptime("15:00", "%H:%M")

    nsppd_risk = calculate_crowd_risk(nsppd["capacity"], afternoon, nsppd)
    test_risk = calculate_crowd_risk(test_event["capacity"], afternoon, test_event)

    assert nsppd_risk["score"] > test_risk["score"]
    assert "Large event capacity" in nsppd_risk["reasons"]
    assert "Large event capacity" not in test_risk["reasons"]


def test_overnight_arrival_format():
    departure = datetime.strptime("08:00", "%H:%M")
    assert format_arrival(departure, 120) == "10:00"
    assert format_arrival(departure, 20 * 60 + 3).startswith("04:03")
    assert "(+1 day)" in format_arrival(departure, 20 * 60 + 3)


def test_calculate_journey_accepts_event():
    event = event_to_public(get_event(DEFAULT_EVENT_ID))
    result = calculate_journey(
        normal_minutes=100,
        departure_time=datetime.strptime("08:00", "%H:%M"),
        direction="outbound",
        event=event,
    )
    assert result["arrival_time"] == "09:40"
    assert result["label"] == "Normal / early departure"


if __name__ == "__main__":
    tests = [
        test_event_store_contains_production_and_test_events,
        test_alias_resolves_to_nsppd,
        test_engine_uses_selected_event_windows,
        test_return_window_follows_event_traffic_end,
        test_crowd_risk_uses_event_capacity_and_window,
        test_overnight_arrival_format,
        test_calculate_journey_accepts_event,
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
    print(len(tests), "tests passed")
