from datetime import datetime

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.data_sources import (
    get_parking_options,
    get_routes,
    get_tfgm_road_conditions,
)
from backend.event_model import JourneyRequest
from backend.event_store import (
    DEFAULT_EVENT_ID,
    event_to_public,
    event_to_summary,
    get_default_event,
    get_event,
    search_events,
)
from backend.travel_engine import calculate_crowd_risk, calculate_journey


app = FastAPI(
    title="Event Travel Intelligence API",
    description="Travel intelligence for major events.",
    version="1.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://aboladvisuals.github.io",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https://.*\.github\.io",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    event = get_default_event()
    return {
        "name": "Event Travel Intelligence API",
        "status": "online",
        "version": "1.3.0",
        "event": event.name,
        "venue": event.venue,
        "default_event_id": event.event_id,
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/events")
def events(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
):
    return [event_to_summary(event) for event in search_events(date_from=date_from, date_to=date_to)]


@app.get("/events/search")
def events_search(
    q: Optional[str] = None,
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


@app.post("/analyze")
def analyze_journey(request: JourneyRequest):
    try:
        departure_time = datetime.strptime(request.departure_time, "%H:%M")
        return_time = datetime.strptime(request.return_time, "%H:%M")

        start_location = request.start_location.strip()
        if not start_location:
            raise ValueError("A starting location is required.")

        try:
            event = get_event(request.event_id or DEFAULT_EVENT_ID)
        except KeyError:
            raise HTTPException(status_code=404, detail="Event not found")

        public_event = event_to_public(event)
        destination = event.destination

        outbound_bundle = get_routes(start_location, destination)
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

        return_bundle = get_routes(destination, start_location)
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
        road_conditions = get_tfgm_road_conditions()

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
                "Journey times are event-adjusted estimates based on a normal "
                "OSRM driving time, an event timing factor and additional "
                "event-related delay. They are not measured live traffic speeds."
            ),
            "parking_disclaimer": (
                "Parking availability is currently not live occupancy data."
            ),
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
            "road_conditions": {
                "source": road_conditions.get("source", "TfGM"),
                "status": road_conditions.get("status"),
                "checked": road_conditions.get("checked"),
                "note": (
                    "TfGM is used as the source attribution for verified "
                    "disruption records. Live page scrapes are not treated "
                    "as measured traffic speeds."
                ),
            },
        }

    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {error}",
        )
