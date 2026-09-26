"""Live parking intelligence.

Occupancy is only labelled live when an official feed returns a state for
that specific facility. Access-time estimates stay independent of occupancy.
"""

import os
import time

import requests

from backend.live_transport import age_minutes, iso_now, is_stale


USER_AGENT = (
    "EventTravelIntelligence/1.5 "
    "(https://github.com/aboladvisuals/event-travel-intelligence)"
)
TFGM_CARPARKS_URL = "https://api.tfgm.com/odata/carparks"
UNKNOWN_AVAILABILITY = "Unknown / No live occupancy feed"
LIVE_CACHE_SECONDS = 300
_CACHE = {}


def _normalise_name(value):
    text = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in str(value or ""))
    return " ".join(text.replace("park and ride", "park ride").replace("p r", "park ride").split())


def unavailable_occupancy(reason=None, source="None configured", checked_at=None):
    checked = checked_at or iso_now()
    return {
        "live": False,
        "status": "unavailable",
        "occupancy": None,
        "availability": UNKNOWN_AVAILABILITY,
        "spaces_remaining": None,
        "source": source,
        "checked_at": checked,
        "age_minutes": age_minutes(checked),
        "note": reason or "No reliable live occupancy feed is configured for this facility.",
    }


def live_occupancy(state, source, checked_at=None, spaces_remaining=None, note=None):
    checked = checked_at or iso_now()
    stale = is_stale(checked)
    availability = UNKNOWN_AVAILABILITY if stale or not state else state
    return {
        "live": bool(state) and not stale,
        "status": "stale" if stale else "live",
        "occupancy": None if stale else state,
        "availability": availability,
        "spaces_remaining": None if stale else spaces_remaining,
        "source": source,
        "checked_at": checked,
        "age_minutes": age_minutes(checked),
        "note": note or ("Live occupancy from an official feed." if not stale else "Occupancy feed is stale."),
    }


def map_occupancy_state(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return None
    text = str(raw).strip()
    if not text:
        return None
    compact = text.lower().replace("_", " ").replace("-", " ")
    if compact in {"available", "spaces available", "plenty", "empty", "open"}:
        return "Available"
    if compact in {"limited", "almost full", "busy", "filling"}:
        return "Limited"
    if compact in {"full", "closed", "no spaces", "full capacity"}:
        return "Full"
    if "full" in compact:
        return "Full"
    if "limited" in compact or "almost" in compact:
        return "Limited"
    if "available" in compact or compact == "open":
        return "Available"
    return None


def extract_spaces_remaining(record):
    if not isinstance(record, dict):
        return None
    for key in (
        "spacesRemaining",
        "SpacesRemaining",
        "spaces_available",
        "SpacesAvailable",
        "freeSpaces",
        "FreeSpaces",
        "availableSpaces",
        "AvailableSpaces",
    ):
        value = record.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return number
    return None


def parse_tfgm_carpark_record(item, checked_at=None):
    if not isinstance(item, dict):
        return None
    name = item.get("name") or item.get("Name") or item.get("title") or item.get("Title")
    if not name:
        return None
    raw_state = (
        item.get("occupancy")
        or item.get("Occupancy")
        or item.get("status")
        or item.get("Status")
        or item.get("availability")
        or item.get("Availability")
        or item.get("state")
        or item.get("State")
    )
    state = map_occupancy_state(raw_state)
    if state is None:
        return None
    return {
        "name": name,
        "match_key": _normalise_name(name),
        "occupancy": live_occupancy(
            state,
            source="TfGM",
            checked_at=checked_at,
            spaces_remaining=extract_spaces_remaining(item),
            note="Occupancy state is the value returned by the TfGM car parks feed.",
        ),
    }


def fetch_tfgm_carparks(fetcher=None):
    key = os.getenv("TFGM_API_KEY")
    app_key = os.getenv("TFGM_APP_KEY")
    checked = iso_now()
    if not key:
        return {
            "available": False,
            "status": "unavailable",
            "items": [],
            "source": "TfGM car parks",
            "checked_at": checked,
            "note": (
                "TfGM car-park occupancy requires TFGM_API_KEY. "
                "The public TfGM open-data portal no longer issues new realtime keys, "
                "and api.tfgm.com/odata/carparks returns Forbidden without credentials."
            ),
        }
    fetch = fetcher or (
        lambda url, headers=None: requests.get(url, headers=headers, timeout=15)
    )
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Ocp-Apim-Subscription-Key": key,
    }
    if app_key:
        headers["AppKey"] = app_key
        headers["DevKey"] = key
    try:
        response = fetch(TFGM_CARPARKS_URL, headers=headers)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("value") if isinstance(payload, dict) else payload
        items = []
        for row in rows or []:
            parsed = parse_tfgm_carpark_record(row, checked_at=checked)
            if parsed:
                items.append(parsed)
        return {
            "available": bool(items),
            "status": "live" if items else "unavailable",
            "items": items,
            "source": "TfGM car parks",
            "checked_at": checked,
            "note": (
                "Live occupancy is only attached when a feed record matches a configured site by name."
                if items
                else "TfGM returned no occupancy states that could be mapped."
            ),
        }
    except Exception as error:
        return {
            "available": False,
            "status": "unavailable",
            "items": [],
            "source": "TfGM car parks",
            "checked_at": checked,
            "note": f"TfGM car-park request failed: {error}",
        }


def match_occupancy(site_name, live_items):
    target = _normalise_name(site_name)
    if not target:
        return None
    for item in live_items or []:
        key = item.get("match_key") or _normalise_name(item.get("name"))
        if not key:
            continue
        if key == target or target in key or key in target:
            return item.get("occupancy")
    return None


def attach_occupancy(site, occupancy):
    payload = dict(site or {})
    record = occupancy or unavailable_occupancy()
    payload["occupancy"] = record.get("occupancy")
    payload["availability"] = record.get("availability") or UNKNOWN_AVAILABILITY
    payload["spaces_remaining"] = record.get("spaces_remaining")
    payload["source"] = record.get("source") or "None configured"
    payload["checked_at"] = record.get("checked_at")
    payload["age_minutes"] = record.get("age_minutes")
    payload["live"] = bool(record.get("live"))
    payload["occupancy_status"] = record.get("status") or "unavailable"
    payload["occupancy_note"] = record.get("note")
    return payload


def get_live_parking(force_refresh=False, fetcher=None):
    cached = _CACHE.get("parking")
    now = time.time()
    if cached and not force_refresh and now - cached["stored_at"] < LIVE_CACHE_SECONDS:
        payload = dict(cached["payload"])
        payload["from_cache"] = True
        return payload
    feed = fetch_tfgm_carparks(fetcher=fetcher)
    payload = {
        "feed": feed,
        "checked_at": feed.get("checked_at"),
        "from_cache": False,
        "limitations": (
            "Greater Manchester Park & Ride locations are published by TfGM as "
            "static map data. Manchester City Council parking files are annual "
            "space counts, not occupancy. The TfGM car-parks API needs a key "
            "and currently returns Forbidden without one. Facilities without a "
            "matching live record stay Unknown / No live occupancy feed."
        ),
    }
    _CACHE["parking"] = {"stored_at": now, "payload": payload}
    return payload


def enrich_parking_sites(sites, live_feed=None):
    feed = live_feed if live_feed is not None else get_live_parking()
    items = ((feed.get("feed") or {}).get("items")) if isinstance(feed, dict) else []
    enriched = []
    for site in sites or []:
        occupancy = match_occupancy(site.get("name"), items)
        if occupancy is None:
            occupancy = unavailable_occupancy(
                reason=(feed.get("feed") or {}).get("note") if isinstance(feed, dict) else None,
                source=(feed.get("feed") or {}).get("source") if isinstance(feed, dict) else "None configured",
                checked_at=(feed.get("checked_at") if isinstance(feed, dict) else None),
            )
        enriched.append(attach_occupancy(site, occupancy))
    return enriched


def clear_parking_cache():
    _CACHE.clear()
