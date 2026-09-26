from datetime import datetime, timedelta, timezone

from backend.event_store import event_to_public, get_event
from backend.parking_intelligence import (
    UNKNOWN_AVAILABILITY,
    attach_occupancy,
    enrich_parking_sites,
    extract_spaces_remaining,
    fetch_tfgm_carparks,
    live_occupancy,
    map_occupancy_state,
    match_occupancy,
    parse_tfgm_carpark_record,
    unavailable_occupancy,
)


def test_unavailable_feed_keeps_unknown_label():
    site = {
        "name": "Ladywell Park & Ride",
        "location": "Ladywell, Manchester, UK",
        "drive_minutes": 115,
        "transfer_minutes": 25,
        "total_access_minutes": 140,
    }
    result = attach_occupancy(site, unavailable_occupancy())
    assert result["availability"] == UNKNOWN_AVAILABILITY
    assert result["live"] is False
    assert result["occupancy"] is None
    assert result["spaces_remaining"] is None
    assert result["drive_minutes"] == 115
    assert result["total_access_minutes"] == 140


def test_live_state_uses_source_value_only():
    occupancy = live_occupancy("Available", source="TfGM", spaces_remaining=42)
    result = attach_occupancy(
        {"name": "Ladywell Park & Ride", "drive_minutes": 115, "transfer_minutes": 25, "total_access_minutes": 140},
        occupancy,
    )
    assert result["availability"] == "Available"
    assert result["occupancy"] == "Available"
    assert result["spaces_remaining"] == 42
    assert result["source"] == "TfGM"
    assert result["live"] is True
    assert result["drive_minutes"] == 115


def test_spaces_remaining_only_when_source_provides_number():
    assert extract_spaces_remaining({"SpacesAvailable": 12}) == 12
    assert extract_spaces_remaining({"availability": "Available"}) is None
    assert extract_spaces_remaining({"spacesRemaining": "full"}) is None


def test_stale_occupancy_is_not_shown_as_live():
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    occupancy = live_occupancy("Full", source="TfGM", checked_at=old, spaces_remaining=0)
    assert occupancy["live"] is False
    assert occupancy["status"] == "stale"
    assert occupancy["availability"] == UNKNOWN_AVAILABILITY
    assert occupancy["spaces_remaining"] is None


def test_event_specific_parking_is_used():
    nsppd = event_to_public(get_event("nsppd-uk-old-trafford-2026"))
    test_event = event_to_public(get_event("test-event-manchester"))
    nsppd_names = [site["name"] for site in nsppd["parking_options"]]
    test_names = [site["name"] for site in test_event["parking_options"]]
    assert "Ladywell Park & Ride" in nsppd_names
    assert test_names == ["Test Park & Ride"]
    assert "Ladywell Park & Ride" not in test_names


def test_enrich_matches_only_named_site():
    live_feed = {
        "feed": {
            "items": [
                {
                    "name": "Ladywell Park & Ride",
                    "match_key": "ladywell park ride",
                    "occupancy": live_occupancy("Limited", source="TfGM"),
                }
            ],
            "source": "TfGM car parks",
            "note": "mapped",
        },
        "checked_at": "2026-09-26T08:00:00Z",
    }
    sites = [
        {"name": "Ladywell Park & Ride", "drive_minutes": 115, "transfer_minutes": 25, "total_access_minutes": 140},
        {"name": "Parkway Park & Ride", "drive_minutes": 110, "transfer_minutes": 25, "total_access_minutes": 135},
    ]
    results = enrich_parking_sites(sites, live_feed=live_feed)
    assert results[0]["availability"] == "Limited"
    assert results[0]["live"] is True
    assert results[1]["availability"] == UNKNOWN_AVAILABILITY
    assert results[1]["live"] is False
    assert results[1]["total_access_minutes"] == 135


def test_api_failure_does_not_invent_occupancy():
    import os

    class Boom:
        def raise_for_status(self):
            raise RuntimeError("API failure")

        def json(self):
            return {}

    previous = os.environ.get("TFGM_API_KEY")
    os.environ["TFGM_API_KEY"] = "test-key-not-secret"
    try:
        feed = fetch_tfgm_carparks(fetcher=lambda url, headers=None: Boom())
    finally:
        if previous is None:
            os.environ.pop("TFGM_API_KEY", None)
        else:
            os.environ["TFGM_API_KEY"] = previous
    assert feed["available"] is False
    assert feed["items"] == []
    assert "failed" in feed["note"].lower()


def test_parse_ignores_records_without_occupancy_state():
    checked = "2026-09-26T08:00:00Z"
    parsed = parse_tfgm_carpark_record({"Name": "Ladywell"}, checked_at=checked)
    assert parsed is None
    parsed = parse_tfgm_carpark_record(
        {"Name": "Ladywell Park & Ride", "Status": "Available", "SpacesAvailable": 18},
        checked_at=checked,
    )
    assert parsed["occupancy"]["availability"] == "Available"
    assert parsed["occupancy"]["spaces_remaining"] == 18


def test_map_occupancy_state_known_values():
    assert map_occupancy_state("available") == "Available"
    assert map_occupancy_state("LIMITED") == "Limited"
    assert map_occupancy_state("full") == "Full"
    assert map_occupancy_state(None) is None
    assert map_occupancy_state("unknown mystery") is None


def test_match_requires_name_overlap():
    items = [{
        "name": "Ladywell Park & Ride",
        "match_key": "ladywell park ride",
        "occupancy": live_occupancy("Available", source="TfGM"),
    }]
    assert match_occupancy("Ladywell Park & Ride", items)["availability"] == "Available"
    assert match_occupancy("Test Park & Ride", items) is None


if __name__ == "__main__":
    tests = [
        test_unavailable_feed_keeps_unknown_label,
        test_live_state_uses_source_value_only,
        test_spaces_remaining_only_when_source_provides_number,
        test_stale_occupancy_is_not_shown_as_live,
        test_event_specific_parking_is_used,
        test_enrich_matches_only_named_site,
        test_api_failure_does_not_invent_occupancy,
        test_parse_ignores_records_without_occupancy_state,
        test_map_occupancy_state_known_values,
        test_match_requires_name_overlap,
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
    print(len(tests), "parking intelligence tests passed")
