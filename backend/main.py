from backend.data_sources import (
    get_route,
    get_parking_options,
    get_tfgm_road_conditions,
)

from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.travel_engine import calculate_journey, calculate_crowd_risk
from backend.data_sources import (
    get_route,
    get_parking_options,
    get_tfgm_road_conditions,
)
from backend.event_config import EVENT


app = FastAPI(
    title="Event Travel Intelligence API",
    description="Travel intelligence for major events.",
    version="1.0.0",
)


class JourneyRequest(BaseModel):
    start_location: str
    departure_time: str
    return_time: str


@app.get("/")
def root():
    return {
        "name": "Event Travel Intelligence API",
        "status": "online",
        "version": "1.0.0",
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

        destination = EVENT["destination"]

        outbound_route = get_route(
            request.start_location,
            destination,
        )

        outbound = calculate_journey(
            normal_minutes=outbound_route["duration_minutes"],
            departure_time=departure_time,
            direction="outbound",
        )

        return_route = get_route(
            destination,
            request.start_location,
        )

        return_journey = calculate_journey(
            normal_minutes=return_route["duration_minutes"],
            departure_time=return_time,
            direction="return",
        )

        crowd = calculate_crowd_risk(
            event_capacity=EVENT["capacity"],
            departure_time=departure_time,
        )

        parking = get_parking_options(
            request.start_location,
        )
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
                "start_location": request.start_location,
                "departure_time": request.departure_time,
                "return_time": request.return_time,
            },

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
            "road_conditions": road_conditions,
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