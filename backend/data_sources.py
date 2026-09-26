import time

import requests
from bs4 import BeautifulSoup


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = (
    "EventTravelIntelligence/1.0 "
    "(https://github.com/aboladvisuals/event-travel-intelligence)"
)

_GEOCODE_CACHE = {}
_LAST_NOMINATIM_CALL = 0.0

UK_HINTS = (
    "uk",
    "u.k.",
    "united kingdom",
    "great britain",
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "gb",
)

INTERNATIONAL_HINTS = (
    "united states",
    "usa",
    "u.s.a",
    "u.s.",
    "america",
    "canada",
    "australia",
    "new zealand",
    "ireland",
    "france",
    "germany",
    "spain",
    "italy",
    "portugal",
    "netherlands",
    "belgium",
    "switzerland",
    "austria",
    "sweden",
    "norway",
    "denmark",
    "poland",
    "india",
    "pakistan",
    "nigeria",
    "ghana",
    "kenya",
    "south africa",
    "japan",
    "china",
    "singapore",
    "uae",
    "dubai",
    "qatar",
    "brazil",
    "mexico",
    "virginia",
    "california",
    "texas",
    "new york",
    "florida",
)


def _nominatim_get(params):
    global _LAST_NOMINATIM_CALL

    elapsed = time.time() - _LAST_NOMINATIM_CALL
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    last_error = None
    for attempt in range(3):
        _LAST_NOMINATIM_CALL = time.time()
        response = requests.get(
            NOMINATIM_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if response.status_code == 429:
            last_error = requests.HTTPError(
                "429 Client Error: Too many requests for url: "
                f"{response.url}"
            )
            time.sleep(2 * (attempt + 1))
            continue
        response.raise_for_status()
        return response

    raise last_error


def _normalise_location(location):
    return " ".join(location.strip().lower().split())


def _looks_explicitly_international(location):
    text = " " + _normalise_location(location) + " "
    if any(" " + hint + " " in text or text.endswith(" " + hint + " ") for hint in UK_HINTS):
        return False
    compact = _normalise_location(location)
    if any(hint in compact for hint in UK_HINTS):
        return False
    return any(hint in compact for hint in INTERNATIONAL_HINTS)


def _search_nominatim(location, countrycodes=None):
    params = {
        "q": location,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    if countrycodes:
        params["countrycodes"] = countrycodes
    response = _nominatim_get(params)
    return response.json()


def get_coordinates(location):
    key = _normalise_location(location)
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]

    results = []
    if not _looks_explicitly_international(location):
        results = _search_nominatim(location, countrycodes="gb")

    if not results:
        results = _search_nominatim(location)

    if not results:
        raise ValueError(f"Location not found: {location}")

    coords = {
        "latitude": float(results[0]["lat"]),
        "longitude": float(results[0]["lon"]),
        "display_name": results[0]["display_name"],
    }
    _GEOCODE_CACHE[key] = coords
    return coords


def get_route(start, destination):
    start_coords = get_coordinates(start)
    destination_coords = get_coordinates(destination)

    url = (
        f"{OSRM_BASE}/"
        f"{start_coords['longitude']},{start_coords['latitude']};"
        f"{destination_coords['longitude']},{destination_coords['latitude']}"
    )

    response = requests.get(
        url,
        params={"overview": "false"},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("No driving route found.")

    route = data["routes"][0]
    return {
        "distance_miles": round(route["distance"] / 1609.344, 1),
        "duration_minutes": round(route["duration"] / 60),
        "start": start_coords,
        "destination": destination_coords,
    }


def get_tfgm_event_info():
    """
    Retrieve basic event information from TfGM.
    """
    url = "https://tfgm.com/"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        return {
            "source": "TfGM",
            "status": "available",
            "page_text_available": bool(text),
        }
    except requests.RequestException:
        return {
            "source": "TfGM",
            "status": "unavailable",
            "page_text_available": False,
        }


PARK_AND_RIDE = [
    {
        "name": "Ladywell Park & Ride",
        "location": "Ladywell, Manchester, UK",
        "transfer_minutes": 25,
    },
    {
        "name": "Parkway Park & Ride",
        "location": "Parkway, Manchester, UK",
        "transfer_minutes": 25,
    },
    {
        "name": "Sale Water Park Park & Ride",
        "location": "Sale Water Park, Manchester, UK",
        "transfer_minutes": 20,
    },
]


AVAILABILITY_LABEL = "Unknown / No live occupancy feed"


def get_parking_options(start_location):
    """
    Calculate access times to available Park & Ride options.

    Parking occupancy is deliberately not invented when
    live data is unavailable.
    """
    options = []

    for parking in PARK_AND_RIDE:
        try:
            route = get_route(start_location, parking["location"])
            total_minutes = (
                route["duration_minutes"] + parking["transfer_minutes"]
            )
            options.append(
                {
                    "name": parking["name"],
                    "location": parking["location"],
                    "distance_miles": route["distance_miles"],
                    "drive_minutes": route["duration_minutes"],
                    "transfer_minutes": parking["transfer_minutes"],
                    "total_access_minutes": total_minutes,
                    "availability": AVAILABILITY_LABEL,
                }
            )
        except (requests.RequestException, ValueError):
            options.append(
                {
                    "name": parking["name"],
                    "location": parking["location"],
                    "distance_miles": None,
                    "drive_minutes": None,
                    "transfer_minutes": parking["transfer_minutes"],
                    "total_access_minutes": None,
                    "availability": AVAILABILITY_LABEL,
                }
            )

    return options


def get_tfgm_road_conditions():
    """
    Retrieve current TfGM road/travel information.

    This provides a source/status layer.
    We do not invent traffic speeds or congestion values.
    """
    url = (
        "https://tfgm.com/travel-updates/"
        "travel-alerts?mode=bus&no-script=true"
    )

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        response.raise_for_status()
        return {
            "source": "TfGM",
            "status": "available",
            "checked": True,
        }
    except requests.RequestException as error:
        return {
            "source": "TfGM",
            "status": "unavailable",
            "checked": False,
            "summary": str(error),
        }
