import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from backend.event_model import Event


DEFAULT_EVENT_ID = "nsppd-uk-old-trafford-2026"
EVENT_ALIASES = {
    "nspdp-uk-old-trafford-2026": DEFAULT_EVENT_ID,
}

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = REPO_ROOT / "data" / "events"


def _normalise_id(event_id: str) -> str:
    return EVENT_ALIASES.get(event_id, event_id)


@lru_cache(maxsize=1)
def load_events() -> Dict[str, Event]:
    events: Dict[str, Event] = {}
    if not EVENTS_DIR.exists():
        return events
    for path in sorted(EVENTS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        event = Event.model_validate(payload)
        events[event.event_id] = event
    return events


def list_events() -> List[Event]:
    events = load_events()
    ordered = []
    if DEFAULT_EVENT_ID in events:
        ordered.append(events[DEFAULT_EVENT_ID])
    for event_id, event in events.items():
        if event_id != DEFAULT_EVENT_ID:
            ordered.append(event)
    return ordered


def get_event(event_id: str = None) -> Event:
    events = load_events()
    resolved_id = _normalise_id(event_id or DEFAULT_EVENT_ID)
    event = events.get(resolved_id)
    if event is None:
        raise KeyError(f"Unknown event: {event_id}")
    return event


def get_default_event() -> Event:
    return get_event(DEFAULT_EVENT_ID)


def event_to_summary(event: Event) -> dict:
    return {
        "event_id": event.event_id,
        "name": event.name,
        "venue": event.venue,
        "city": event.city,
        "country": event.country,
        "date": event.date,
        "capacity": event.capacity,
        "destination": event.destination,
        "fictional": event.fictional,
    }


def search_events(query: str = None, date_from: str = None, date_to: str = None):
    events = list_events()
    if date_from:
        events = [event for event in events if event.date >= date_from]
    if date_to:
        events = [event for event in events if event.date <= date_to]
    needle = (query or "").strip().lower()
    if not needle:
        return events
    matches = []
    for event in events:
        haystack = " ".join(
            [
                event.name,
                event.venue,
                event.city,
                event.country,
                event.destination,
            ]
        ).lower()
        if needle in haystack:
            matches.append(event)
    return matches


def event_to_public(event: Event) -> dict:
    return {
        "event_id": event.event_id,
        "name": event.name,
        "venue": event.venue,
        "city": event.city,
        "country": event.country,
        "date": event.date,
        "capacity": event.capacity,
        "destination": event.destination,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "traffic_management_start": event.traffic_management_start,
        "traffic_management_end": event.traffic_management_end,
        "traffic_management": {
            "start": event.traffic_management_start,
            "end": event.traffic_management_end,
        },
        "verified_disruptions": [item.model_dump() for item in event.disruptions],
        "disruptions": [item.model_dump() for item in event.disruptions],
        "parking": {
            option.name.lower().replace(" ", "_").replace("&", "and"): option.model_dump()
            for option in event.parking_options
        },
        "parking_options": [option.model_dump() for option in event.parking_options],
        "fictional": event.fictional,
    }
