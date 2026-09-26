from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.data_sources import (
    get_parking_options,
    get_route,
    get_tfgm_road_conditions,
)
from backend.event_config import EVENT
from backend.travel_engine import calculate_crowd_risk, calculate_journey


app = FastAPI(
    title="Event Travel Intelligence API",
    description="Travel intelligence for major events.",
    version="1.0.1",
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


class JourneyRequest(BaseModel):
    start_location: str = Field(..., min_length=1)
    departure_time: str
    return_time: str
    destination: Optional[str] = None
    event_capacity: Optional[int] = None


@app.get("/")
def root():
    return {
        "name": "Event Travel Intelligence API",
        "status": "online",
        "version": "1.0.1",
        "event": EVENT["name"],
        "venue": EVENT["venue"],
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/event")
def get_event():
    return EVENT


@app.post("/analyze")
def analyze_journey(request: JourneyRequest):
    try:
        departure_time = datetime.strptime(
            request.departure_time,
            "%H:%M",
        )
        return_time = datetime.strptime(
            request.return_time,
            "%H:%M",
        )

        start_location = request.start_location.strip()
        if not start_location:
            raise ValueError("A starting location is required.")

        destination = EVENT["destination"]

        outbound_route = get_route(start_location, destination)
        outbound = calculate_journey(
            normal_minutes=outbound_route["duration_minutes"],
            departure_time=departure_time,
            direction="outbound",
        )

        return_route = get_route(destination, start_location)
        return_journey = calculate_journey(
            normal_minutes=return_route["duration_minutes"],
            departure_time=return_time,
            direction="return",
        )

        crowd = calculate_crowd_risk(
            event_capacity=EVENT["capacity"],
            departure_time=departure_time,
        )

        parking = get_parking_options(start_location)
        road_conditions = get_tfgm_road_conditions()

        return {
            "event": {
                "name": EVENT["name"],
                "venue": EVENT["venue"],
                "city": EVENT["city"],
                "date": EVENT["date"],
                "capacity": EVENT["capacity"],
                "destination": destination,
                "traffic_management": EVENT["traffic_management"],
                "verified_disruptions": EVENT["verified_disruptions"],
            },
            "request": {
                "start_location": start_location,
                "resolved_start": outbound_route["start"]["display_name"],
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
                "distance_miles": outbound_route["distance_miles"],
                **outbound,
            },
            "return": {
                "distance_miles": return_route["distance_miles"],
                **return_journey,
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

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {error}",
        )
