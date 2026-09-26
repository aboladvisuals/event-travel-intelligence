from backend.event_store import event_to_public, get_default_event


EVENT = event_to_public(get_default_event())
DEFAULT_EVENT_ID = "nsppd-uk-old-trafford-2026"
