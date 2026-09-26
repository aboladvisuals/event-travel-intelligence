from datetime import datetime

from backend.data_sources import _route_summary
from backend.travel_engine import (
    calculate_journey,
    format_arrival,
    journey_breakdown,
)


def test_breakdown_sums_to_estimate():
    breakdown = journey_breakdown(123, 158, 10)
    assert breakdown["normal_minutes"] == 123
    assert breakdown["event_impact_minutes"] == 25
    assert breakdown["extra_delay_minutes"] == 10
    assert breakdown["estimated_minutes"] == 158
    assert (
        breakdown["normal_minutes"]
        + breakdown["event_impact_minutes"]
        + breakdown["extra_delay_minutes"]
        == breakdown["estimated_minutes"]
    )


def test_early_journey_has_zero_event_impact():
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
    assert result["estimated_minutes"] == 123
    assert result["breakdown"]["event_impact_minutes"] == 0
    assert result["breakdown"]["extra_delay_minutes"] == 0
    assert result["day_rollover"] is False
    assert result["arrival_time"] == "10:03"


def test_return_peak_includes_extra_delay_and_rollover():
    result = calculate_journey(
        normal_minutes=123,
        departure_time=datetime.strptime("20:30", "%H:%M"),
        direction="return",
        event={
            "traffic_management_start": "11:30",
            "traffic_management_end": "21:00",
        },
    )
    assert result["extra_delay"] == 60
    assert result["breakdown"]["extra_delay_minutes"] == 60
    assert (
        result["normal_minutes"]
        + result["breakdown"]["event_impact_minutes"]
        + result["breakdown"]["extra_delay_minutes"]
        == result["estimated_minutes"]
    )
    assert result["day_rollover"] is True
    assert "(+1 day)" in result["arrival_time"]


def test_overnight_format_unchanged():
    departure = datetime.strptime("08:00", "%H:%M")
    assert format_arrival(departure, 120) == "10:00"
    assert "(+1 day)" in format_arrival(departure, 20 * 60 + 3)


def test_route_summary_swaps_geojson_to_leaflet_order():
    summary = _route_summary(
        {
            "distance": 16093.44,
            "duration": 3600,
            "geometry": {"coordinates": [[-2.29, 53.46], [-1.47, 53.80]]},
        },
        index=1,
        include_geometry=True,
    )
    assert summary["label"] == "Alternative 1"
    assert summary["distance_miles"] == 10.0
    assert summary["duration_minutes"] == 60
    assert summary["geometry"] == [[53.46, -2.29], [53.80, -1.47]]


if __name__ == "__main__":
    tests = [
        test_breakdown_sums_to_estimate,
        test_early_journey_has_zero_event_impact,
        test_return_peak_includes_extra_delay_and_rollover,
        test_overnight_format_unchanged,
        test_route_summary_swaps_geojson_to_leaflet_order,
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
    print(len(tests), "journey intelligence tests passed")
