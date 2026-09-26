import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.data_sources import (
    get_parking_options,
    get_routes,
)
from backend.db import ping, stats as db_stats, sync_events
from backend.event_model import JourneyRequest
from backend.event_store import (
    DEFAULT_EVENT_ID,
    event_to_public,
    event_to_summary,
    get_default_event,
    get_event,
    list_events,
    search_events,
)
from backend.live_transport import (
    attach_live_to_journey,
    get_live_transport,
)
from backend.observability import RequestLogMiddleware, configure_logging, log_event
from backend.parking_intelligence import get_live_parking
from backend.rate_limit import RateLimitMiddleware
from backend.settings import (
    APP_NAME,
    APP_VERSION,
    allowed_origin_regex,
    allowed_origins,
    configured_key_flags,
    debug_errors,
    redis_url,
)
from backend.cache import backend_name as cache_backend
from backend.travel_engine import calculate_crowd_risk, calculate_journey, format_arrival


configure_logging()
LOGGER = logging.getLogger("eti")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        sync_events(list_events())
        log_event(LOGGER, "info", "startup", events=len(list_events()), cache=cache_backend())
    except Exception as error:
        log_event(LOGGER, "error", "startup_sync_failed", error=str(error))
    yield


app = FastAPI(
    title=APP_NAME,
    description="Travel intelligence for major events.",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_origin_regex=allowed_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _public_error(status_code, detail):
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _public_error(422, "Invalid request. Check location and time fields.")


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return _public_error(exc.status_code, exc.detail)
    log_event(LOGGER, "error", "unhandled_error", path=str(request.url.path), error=type(exc).__name__)
    detail = str(exc) if debug_errors() else "Internal server error"
    return _public_error(500, detail)


@app.get("/")
def root():
    event = get_default_event()
    return {
        "name": APP_NAME,
        "status": "online",
        "version": APP_VERSION,
        "event": event.name,
        "venue": event.venue,
        "default_event_id": event.event_id,
    }


@app.get("/health")
def health():
    database = db_stats()
    status = "healthy" if database.get("ok") else "degraded"
    return {
        "status": status,
        "version": APP_VERSION,
        "database": database,
        "cache": {"backend": cache_backend()},
        "redis_configured": bool(redis_url()),
        "keys_configured": configured_key_flags(),
        "default_event_id": DEFAULT_EVENT_ID,
    }


@app.get("/ready")
def ready():
    if not ping():
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        get_default_event()
    except KeyError:
        raise HTTPException(status_code=503, detail="Event catalog unavailable")
    return {"status": "ready", "version": APP_VERSION}


@app.get("/events")
def events(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
):
    return [event_to_summary(event) for event in search_events(date_from=date_from, date_to=date_to)]


@app.get("/events/search")
def events_search(
    q: Optional[str] = Query(None, max_length=120),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
):
    return [event_to_summary(event) for event in search_events(q, date_from, date_to)]


@app.get("/events/{event_id}")
def event_by_id(event_id: str):
    try:
        return event_to_public(get_event(event_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")


@app.get("/event")
def get_current_event():
    return event_to_public(get_default_event())


@app.get("/transport/live")
def transport_live():
    return get_live_transport()


@app.get("/parking/live")
def parking_live():
    return get_live_parking()


def _decorate_routes(options, live_traffic):
    decorated = []
    for option in options:
        adjusted = dict(option)
        adjusted["breakdown"] = attach_live_to_journey(
            {"breakdown": option.get("breakdown") or {}, "estimated_minutes": option.get("estimated_minutes")},
            live_traffic,
        )["breakdown"]
        adjusted["estimated_minutes"] = adjusted["breakdown"]["estimated_minutes"]
        decorated.append(adjusted)
    return decorated


@app.post("/analyze")
def analyze_journey(request: JourneyRequest):
    try:
        departure_time = datetime.strptime(request.departure_time, "%H:%M")
        return_time = datetime.strptime(request.return_time, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Times must use HH:MM.")

    start_location = request.start_location.strip()
    if not start_location:
        raise HTTPException(status_code=400, detail="A starting location is required.")

    try:
        event = get_event(request.event_id or DEFAULT_EVENT_ID)
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")

    public_event = event_to_public(event)
    destination = event.destination

    try:
        outbound_bundle = get_routes(start_location, destination)
        return_bundle = get_routes(destination, start_location)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception:
        log_event(LOGGER, "error", "routing_failed")
        raise HTTPException(status_code=502, detail="Routing service is unavailable. Try again shortly.")

    outbound_primary = outbound_bundle["routes"][0]
    outbound = calculate_journey(
        normal_minutes=outbound_primary["duration_minutes"],
        departure_time=departure_time,
        direction="outbound",
        event=public_event,
    )
    outbound_options = []
    for option in outbound_bundle["routes"]:
        adjusted = calculate_journey(
            normal_minutes=option["duration_minutes"],
            departure_time=departure_time,
            direction="outbound",
            event=public_event,
        )
        outbound_options.append({
            "id": option["id"],
            "label": option["label"],
            "distance_miles": option["distance_miles"],
            "normal_minutes": adjusted["normal_minutes"],
            "estimated_minutes": adjusted["estimated_minutes"],
            "breakdown": adjusted["breakdown"],
            "geometry": option.get("geometry") or [],
        })

    return_primary = return_bundle["routes"][0]
    return_journey = calculate_journey(
        normal_minutes=return_primary["duration_minutes"],
        departure_time=return_time,
        direction="return",
        event=public_event,
    )
    return_options = []
    for option in return_bundle["routes"]:
        adjusted = calculate_journey(
            normal_minutes=option["duration_minutes"],
            departure_time=return_time,
            direction="return",
            event=public_event,
        )
        return_options.append({
            "id": option["id"],
            "label": option["label"],
            "distance_miles": option["distance_miles"],
            "normal_minutes": adjusted["normal_minutes"],
            "estimated_minutes": adjusted["estimated_minutes"],
            "breakdown": adjusted["breakdown"],
            "geometry": option.get("geometry") or [],
        })

    crowd = calculate_crowd_risk(
        event_capacity=event.capacity,
        departure_time=departure_time,
        event=public_event,
    )

    parking = get_parking_options(
        start_location,
        parking_options=public_event["parking_options"],
    )

    live = get_live_transport(
        start_coords=outbound_bundle["start"],
        dest_coords=outbound_bundle["destination"],
        event=public_event,
    )
    live_traffic = live.get("live_traffic") or {}
    outbound = attach_live_to_journey(outbound, live_traffic, format_arrival=format_arrival)
    return_journey = attach_live_to_journey(return_journey, live_traffic, format_arrival=format_arrival)
    outbound_options = _decorate_routes(outbound_options, live_traffic)
    return_options = _decorate_routes(return_options, live_traffic)

    return {
        "event": public_event,
        "request": {
            "event_id": event.event_id,
            "start_location": start_location,
            "resolved_start": outbound_bundle["start"]["display_name"],
            "departure_time": request.departure_time,
            "return_time": request.return_time,
        },
        "estimate_disclaimer": (
            "Journey times keep the OSRM normal duration separate from the "
            "event model. Live traffic minutes are included only when a "
            "licensed measured-speed source is configured and returns data."
        ),
        "parking_disclaimer": (
            "Live parking occupancy is shown only when an official feed "
            "returns a state for that facility. Access times are drive plus "
            "transfer estimates and are separate from occupancy."
        ),
        "live_parking": get_live_parking(),
        "outbound": {
            "distance_miles": outbound_primary["distance_miles"],
            "routes": outbound_options,
            **outbound,
        },
        "return": {
            "distance_miles": return_primary["distance_miles"],
            "routes": return_options,
            **return_journey,
        },
        "map": {
            "start": outbound_bundle["start"],
            "destination": outbound_bundle["destination"],
            "outbound_routes": outbound_options,
            "return_routes": return_options,
            "parking": parking,
        },
        "crowd": crowd,
        "parking": parking,
        "live_transport": live,
        "road_conditions": {
            "source": (live.get("sources") or {}).get("tfgm_status", {}).get("source", "TfGM"),
            "status": (live.get("sources") or {}).get("tfgm_status", {}).get("status"),
            "checked": True,
            "checked_at": live.get("checked_at"),
            "note": live.get("limitations"),
        },
    }
