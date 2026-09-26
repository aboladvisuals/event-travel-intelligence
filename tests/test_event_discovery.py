from backend.event_store import (
    event_to_summary,
    get_event,
    search_events,
)


def test_search_manchester_returns_both_events():
    results = {event.event_id: event for event in search_events("Manchester")}
    assert "nsppd-uk-old-trafford-2026" in results
    assert "test-event-manchester" in results


def test_search_nsppd_and_old_trafford():
    nsppd = search_events("NSPPD")
    venue = search_events("Old Trafford")
    assert len(nsppd) == 1
    assert nsppd[0].event_id == "nsppd-uk-old-trafford-2026"
    assert len(venue) == 1
    assert venue[0].venue == "Old Trafford"


def test_search_is_case_insensitive_and_partial():
    assert search_events("old traff")[0].event_id == "nsppd-uk-old-trafford-2026"
    assert search_events("xyz123") == []


def test_empty_search_returns_available_events():
    assert len(search_events("")) == 2
    assert len(search_events(None)) == 2


def test_date_filter_excludes_october_test_event():
    results = search_events(date_from="2026-09-01", date_to="2026-09-30")
    ids = [event.event_id for event in results]
    assert ids == ["nsppd-uk-old-trafford-2026"]


def test_summary_includes_discovery_fields():
    payload = event_to_summary(get_event("nsppd-uk-old-trafford-2026"))
    for field in ("event_id", "name", "venue", "city", "country", "date", "capacity", "destination"):
        assert field in payload
        assert payload[field]


def test_alias_event_lookup_still_works():
    event = get_event("nspdp-uk-old-trafford-2026")
    assert event.event_id == "nsppd-uk-old-trafford-2026"


def test_unknown_event_raises_keyerror():
    try:
        get_event("invalid-event")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


if __name__ == "__main__":
    tests = [
        test_search_manchester_returns_both_events,
        test_search_nsppd_and_old_trafford,
        test_search_is_case_insensitive_and_partial,
        test_empty_search_returns_available_events,
        test_date_filter_excludes_october_test_event,
        test_summary_includes_discovery_fields,
        test_alias_event_lookup_still_works,
        test_unknown_event_raises_keyerror,
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
    print(len(tests), "discovery tests passed")
