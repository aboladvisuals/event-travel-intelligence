from typing import List, Optional

from pydantic import BaseModel, Field


class Disruption(BaseModel):
    title: str
    type: str = "Event traffic"
    start: str
    end: str
    impact: str
    source: str = "TfGM"


class ParkingOption(BaseModel):
    name: str
    location: str
    transfer_minutes: int = 20


class Event(BaseModel):
    event_id: str
    name: str
    venue: str
    city: str
    country: str = "United Kingdom"
    date: str
    capacity: int
    destination: str
    start_time: str
    end_time: str
    traffic_management_start: str
    traffic_management_end: str
    disruptions: List[Disruption] = Field(default_factory=list)
    parking_options: List[ParkingOption] = Field(default_factory=list)
    fictional: bool = False


class EventSummary(BaseModel):
    event_id: str
    name: str
    venue: str
    city: str
    country: str = "United Kingdom"
    date: str
    capacity: int = 0
    destination: str = ""
    fictional: bool = False


class JourneyRequest(BaseModel):
    start_location: str = Field(..., min_length=1, max_length=200)
    departure_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    return_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    event_id: Optional[str] = Field(default=None, max_length=120)
    destination: Optional[str] = Field(default=None, max_length=200)
    event_capacity: Optional[int] = Field(default=None, ge=0, le=500000)
