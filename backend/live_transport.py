"""Live transport intelligence.

Measured traffic speeds and official disruption feeds are used only when a
reliable source is actually available. Static event configuration is never
labelled as live. Missing or failed sources are reported as unavailable.
"""

from datetime import datetime, timezone
from typing import Callable, Optional
import os
import time

import requests


USER_AGENT = (
    "EventTravelIntelligence/1.4 "
    "(https://github.com/aboladvisuals/event-travel-intelligence)"
)

WEBTRIS_SITES_URL = "https://webtris.nationalhighways.co.uk/api/v1.0/sites"
TFGM_STATUS_URL = "https://tfgm.com/travel-updates/travel-alerts?mode=bus&no-script=true"
TFGM_ALERTS_URL = "https://api.tfgm.com/odata/travelalerts"
TOMTOM_ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{path}/json"
NH_CLOSURE_URLS = (
    "https://api.data.nationalhighways.co.uk/tis/v2/roadandlaneclosures",
    "https://api.data.nationalhighways.co.uk/roadandlaneclosures/v2",
)

LIVE_CACHE_SECONDS = 300
STALE_AFTER_MINUTES = 15

_CACHE = {}


def utc_now():
    return datetime.now(timezone.utc)


def iso_now(moment=None):
    moment = moment or utc_now()
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def age_minutes(checked_at, now=None):
    if not checked_at:
        return None
    now = now or utc_now()
    if isinstance(checked_at, str):
        parsed = checked_at.replace("Z", "+00:00")
        checked = datetime.fromisoformat(parsed)
    else:
        checked = checked_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return max(0, int((now - checked).total_seconds() // 60))


def is_stale(checked_at, now=None, limit_minutes=STALE_AFTER_MINUTES):
    minutes = age_minutes(checked_at, now)
    return minutes is None or minutes >= limit_minutes


def _headers():
    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def configured_keys():
    return {
        "national_highways": bool(
            os.getenv("NATIONAL_HIGHWAYS_SUBSCRIPTION_KEY")
            or os.getenv("NATIONAL_HIGHWAYS_API_KEY")
        ),
        "tfgm": bool(os.getenv("TFGM_API_KEY") or os.getenv("TFGM_APP_KEY")),
        "tomtom": bool(os.getenv("TOMTOM_API_KEY")),
    }


def structured_disruption(
    title,
    disruption_type="Disruption",
    affected_road=None,
    location=None,
    start=None,
    end=None,
    severity=None,
    status="active",
    source="Unknown",
    origin="live",
    checked_at=None,
):
    return {
        "title": title,
        "type": disruption_type,
        "affected_road": affected_road,
        "location": location,
        "start": start,
        "end": end,
        "severity": severity,
        "status": status,
        "source": source,
        "origin": origin,
        "checked_at": checked_at or iso_now(),
    }


def configured_disruptions(event, checked_at=None):
    event = event or {}
    records = event.get("verified_disruptions") or event.get("disruptions") or []
    stamped = checked_at or iso_now()
    structured = []
    for item in records:
        structured.append(
            structured_disruption(
                title=item.get("title") or "Configured disruption",
                disruption_type=item.get("type") or "Event traffic",
                affected_road=item.get("affected_road") or item.get("road"),
                location=item.get("location") or item.get("impact"),
                start=item.get("start"),
                end=item.get("end"),
                severity=item.get("severity") or item.get("impact"),
                status="configured",
                source=item.get("source") or "Event configuration",
                origin="configured",
                checked_at=stamped,
            )
        )
    return structured


def live_traffic_unavailable(reason, source="None configured", checked_at=None):
    checked = checked_at or iso_now()
    return {
        "available": False,
        "status": "unavailable",
        "additional_minutes": None,
        "source": source,
        "checked_at": checked,
        "age_minutes": age_minutes(checked),
        "note": reason,
    }


def live_traffic_available(additional_minutes, source, checked_at=None, note=None):
    checked = checked_at or iso_now()
    stale = is_stale(checked)
    return {
        "available": not stale and additional_minutes is not None,
        "status": "stale" if stale else "live",
        "additional_minutes": additional_minutes if not stale else None,
        "reported_minutes": additional_minutes,
        "source": source,
        "checked_at": checked,
        "age_minutes": age_minutes(checked),
        "note": note
        or (
            "Live delay is from a licensed traffic service and is shown separately "
            "from the OSRM normal time."
        ),
    }


def apply_live_traffic(breakdown, live_traffic):
    """Keep OSRM normal time. Add a live delay only when a measured value exists."""
    breakdown = dict(breakdown or {})
    live = live_traffic or {}
    live_minutes = live.get("additional_minutes")
    available = bool(live.get("available") and live_minutes is not None)
    normal = int(breakdown.get("normal_minutes") or 0)
    event_impact = int(breakdown.get("event_impact_minutes") or 0)
    extra = int(breakdown.get("extra_delay_minutes") or 0)
    if available:
        estimated = normal + int(live_minutes) + event_impact + extra
        shown_live = int(live_minutes)
    else:
        estimated = int(
            breakdown.get("estimated_minutes")
            if breakdown.get("estimated_minutes") is not None
            else normal + event_impact + extra
        )
        shown_live = None
    breakdown["live_traffic_minutes"] = shown_live
    breakdown["live_traffic_available"] = available
    breakdown["estimated_minutes"] = estimated
    return breakdown


def attach_live_to_journey(journey, live_traffic, format_arrival=None):
    journey = dict(journey or {})
    breakdown = apply_live_traffic(journey.get("breakdown") or {}, live_traffic)
    journey["breakdown"] = breakdown
    journey["estimated_minutes"] = breakdown["estimated_minutes"]
    if format_arrival and journey.get("departure_time"):
        try:
            departure = datetime.strptime(journey["departure_time"], "%H:%M")
            journey["arrival_time"] = format_arrival(
                departure, breakdown["estimated_minutes"]
            )
        except (TypeError, ValueError):
            pass
    return journey


def _get(url, headers=None, timeout=12, params=None):
    return requests.get(
        url,
        headers=headers or _headers(),
        timeout=timeout,
        params=params,
    )


def check_webtris(fetcher: Optional[Callable] = None):
    fetch = fetcher or _get
    checked = iso_now()
    try:
        response = fetch(WEBTRIS_SITES_URL)
        response.raise_for_status()
        payload = response.json() if hasattr(response, "json") else {}
        count = payload.get("row_count") if isinstance(payload, dict) else None
        return {
            "available": True,
            "status": "available",
            "source": "National Highways WebTRIS",
            "checked_at": checked,
            "age_minutes": 0,
            "note": (
                "WebTRIS is a free National Highways traffic-count API. "
                "It confirms the open-data service is reachable but does not "
                "provide measured journey times for an origin-destination pair."
            ),
            "site_count": count,
        }
    except Exception as error:
        return {
            "available": False,
            "status": "unavailable",
            "source": "National Highways WebTRIS",
            "checked_at": checked,
            "age_minutes": 0,
            "note": f"WebTRIS open-data check failed: {error}",
        }


def check_tfgm_status(fetcher: Optional[Callable] = None):
    fetch = fetcher or _get
    checked = iso_now()
    try:
        response = fetch(TFGM_STATUS_URL)
        response.raise_for_status()
        return {
            "available": True,
            "status": "available",
            "source": "TfGM",
            "checked_at": checked,
            "age_minutes": 0,
            "note": (
                "TfGM travel-updates page is reachable. Page HTML is not parsed "
                "into live incidents and is not treated as measured traffic speed."
            ),
        }
    except Exception as error:
        return {
            "available": False,
            "status": "unavailable",
            "source": "TfGM",
            "checked_at": checked,
            "age_minutes": 0,
            "note": f"TfGM status check failed: {error}",
        }


def fetch_tomtom_live_delay(start_coords, dest_coords, fetcher=None):
    key = os.getenv("TOMTOM_API_KEY")
    if not key:
        return live_traffic_unavailable(
            "No licensed live speed feed is configured. "
            "Set TOMTOM_API_KEY to enable TomTom traffic routing. "
            "National Highways DATEX journey-time feeds also require a subscription key.",
            source="None configured",
        )
    if not start_coords or not dest_coords:
        return live_traffic_unavailable(
            "Live traffic routing needs origin and destination coordinates.",
            source="TomTom Routing",
        )

    fetch = fetcher or (
        lambda url, params=None: requests.get(
            url, params=params, headers=_headers(), timeout=15
        )
    )
    path = (
        f"{start_coords['latitude']},{start_coords['longitude']}:"
        f"{dest_coords['latitude']},{dest_coords['longitude']}"
    )
    url = TOMTOM_ROUTE_URL.format(path=path)
    try:
        live_response = fetch(url, params={"key": key, "traffic": "true"})
        free_response = fetch(url, params={"key": key, "traffic": "false"})
        live_response.raise_for_status()
        free_response.raise_for_status()
        live_payload = live_response.json()
        free_payload = free_response.json()
        live_seconds = live_payload["routes"][0]["summary"]["travelTimeInSeconds"]
        free_seconds = free_payload["routes"][0]["summary"]["travelTimeInSeconds"]
        additional = round((live_seconds - free_seconds) / 60)
        return live_traffic_available(
            additional_minutes=additional,
            source="TomTom Routing",
            note=(
                "Live delay is TomTom traffic travel time minus the same route "
                "without traffic. OSRM normal time is not replaced."
            ),
        )
    except Exception as error:
        return live_traffic_unavailable(
            f"Licensed live speed request failed: {error}",
            source="TomTom Routing",
        )


def _parse_tfgm_alerts(payload, checked_at):
    records = []
    rows = payload.get("value") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return records
    for item in rows[:20]:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("Title") or item.get("name")
        if not title:
            continue
        records.append(
            structured_disruption(
                title=title,
                disruption_type=item.get("type") or item.get("Type") or "Travel alert",
                affected_road=item.get("road") or item.get("Road"),
                location=item.get("location") or item.get("Location"),
                start=item.get("start") or item.get("StartDate"),
                end=item.get("end") or item.get("EndDate"),
                severity=item.get("severity") or item.get("Severity"),
                status=item.get("status") or "active",
                source="TfGM",
                origin="live",
                checked_at=checked_at,
            )
        )
    return records


def _parse_nh_closures(payload, checked_at):
    records = []
    if payload is None:
        return records
    rows = payload
    if isinstance(payload, dict):
        for key in ("value", "features", "situations", "closures", "items"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    if not isinstance(rows, list):
        return records
    for item in rows[:20]:
        if not isinstance(item, dict):
            continue
        props = item.get("properties") if isinstance(item.get("properties"), dict) else item
        title = (
            props.get("title")
            or props.get("name")
            or props.get("situationRecord")
            or props.get("description")
        )
        if not title:
            continue
        records.append(
            structured_disruption(
                title=str(title)[:180],
                disruption_type=props.get("type") or "Road closure",
                affected_road=props.get("road") or props.get("roadNumber"),
                location=props.get("location") or props.get("place"),
                start=props.get("start") or props.get("validityStart"),
                end=props.get("end") or props.get("validityEnd"),
                severity=props.get("severity") or props.get("impact"),
                status=props.get("status") or "active",
                source="National Highways",
                origin="live",
                checked_at=checked_at,
            )
        )
    return records


def fetch_live_disruptions(fetcher=None):
    checked = iso_now()
    records = []
    sources = []
    nh_key = os.getenv("NATIONAL_HIGHWAYS_SUBSCRIPTION_KEY") or os.getenv(
        "NATIONAL_HIGHWAYS_API_KEY"
    )
    if nh_key:
        nh_ok = False
        last_error = None
        for url in NH_CLOSURE_URLS:
            try:
                response = requests.get(
                    url,
                    headers={
                        **_headers(),
                        "Ocp-Apim-Subscription-Key": nh_key,
                    },
                    params={"api-version": "2.0"},
                    timeout=15,
                )
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}"
                    continue
                records.extend(_parse_nh_closures(response.json(), checked))
                sources.append("National Highways Road and Lane Closures")
                nh_ok = True
                break
            except Exception as error:
                last_error = str(error)
        if not nh_ok:
            sources.append(f"National Highways (unavailable: {last_error})")
    else:
        sources.append("National Highways closures (no subscription key configured)")

    tfgm_key = os.getenv("TFGM_API_KEY")
    tfgm_app = os.getenv("TFGM_APP_KEY")
    if tfgm_key:
        try:
            headers = {**_headers(), "Ocp-Apim-Subscription-Key": tfgm_key}
            if tfgm_app:
                headers["AppKey"] = tfgm_app
                headers["DevKey"] = tfgm_key
            response = requests.get(TFGM_ALERTS_URL, headers=headers, timeout=15)
            response.raise_for_status()
            records.extend(_parse_tfgm_alerts(response.json(), checked))
            sources.append("TfGM travel alerts")
        except Exception as error:
            sources.append(f"TfGM travel alerts (unavailable: {error})")
    else:
        sources.append("TfGM travel alerts (no API key configured)")

    return {
        "available": bool(records),
        "status": "live" if records else "unavailable",
        "items": records,
        "source": "; ".join(sources),
        "checked_at": checked,
        "age_minutes": 0,
        "note": (
            "Live disruption records are only created from official feeds that "
            "returned structured data. Event-configuration records are listed "
            "separately and are not labelled live."
        ),
    }


def get_live_transport(start_coords=None, dest_coords=None, event=None, force_refresh=False):
    cache_key = "live"
    cached = _CACHE.get(cache_key)
    now = time.time()
    if cached and not force_refresh and now - cached["stored_at"] < LIVE_CACHE_SECONDS:
        payload = dict(cached["payload"])
        payload["from_cache"] = True
        live = dict(payload.get("live_traffic") or {})
        live["age_minutes"] = age_minutes(live.get("checked_at"))
        if is_stale(live.get("checked_at")):
            live["available"] = False
            live["status"] = "stale"
            live["additional_minutes"] = None
        payload["live_traffic"] = live
        return payload

    checked = iso_now()
    webtris = check_webtris()
    tfgm = check_tfgm_status()
    live_traffic = fetch_tomtom_live_delay(start_coords, dest_coords)
    live_disruptions = fetch_live_disruptions()
    configured = configured_disruptions(event, checked_at=checked)

    payload = {
        "live_traffic": live_traffic,
        "live_disruptions": live_disruptions,
        "configured_disruptions": configured,
        "sources": {
            "webtris": webtris,
            "tfgm_status": tfgm,
            "keys_configured": configured_keys(),
        },
        "checked_at": checked,
        "from_cache": False,
        "limitations": (
            "No free, keyless UK source currently provides measured origin-"
            "destination traffic speeds. WebTRIS is historic/count data. "
            "National Highways DATEX and TfGM alert APIs require subscription "
            "keys. Without those keys, live speed impact is reported as "
            "unavailable and the event-adjusted estimate is used."
        ),
    }
    _CACHE[cache_key] = {"stored_at": now, "payload": payload}
    return payload


def clear_live_cache():
    _CACHE.clear()
