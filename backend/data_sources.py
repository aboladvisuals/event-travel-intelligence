import requests
from bs4 import BeautifulSoup


def get_coordinates(location):
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": location,
        "format": "json",
        "limit": 1,
    }

    headers = {
        "User-Agent": "EventTravelIntelligence/1.0"
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        raise ValueError(f"Location not found: {location}")

    return {
        "latitude": float(results[0]["lat"]),
        "longitude": float(results[0]["lon"]),
        "display_name": results[0]["display_name"],
    }


def get_route(start, destination):
    start_coords = get_coordinates(start)
    destination_coords = get_coordinates(destination)

    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{start_coords['longitude']},{start_coords['latitude']};"
        f"{destination_coords['longitude']},{destination_coords['latitude']}"
    )

    params = {
        "overview": "false",
    }

    response = requests.get(
        url,
        params=params,
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
            headers={
                "User-Agent": "EventTravelIntelligence/1.0"
            },
            timeout=15,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        text = soup.get_text(
            " ",
            strip=True
        )

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


def get_parking_options(start_location):
    """
    Calculate access times to available Park & Ride options.

    Parking occupancy is deliberately not invented when
    live data is unavailable.
    """

    options = []

    for parking in PARK_AND_RIDE:

        try:
            route = get_route(
                start_location,
                parking["location"],
            )

            total_minutes = (
                route["duration_minutes"]
                + parking["transfer_minutes"]
            )

            options.append(
                {
                    "name": parking["name"],
                    "distance_miles": route["distance_miles"],
                    "drive_minutes": route["duration_minutes"],
                    "transfer_minutes": parking["transfer_minutes"],
                    "total_access_minutes": total_minutes,
                    "availability": "Unknown",
                }
            )

        except (requests.RequestException, ValueError):

            options.append(
                {
                    "name": parking["name"],
                    "distance_miles": None,
                    "drive_minutes": None,
                    "transfer_minutes": parking["transfer_minutes"],
                    "total_access_minutes": None,
                    "availability": "Unknown",
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
            headers={
                "User-Agent": "EventTravelIntelligence/1.0"
            },
            timeout=15,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        page_text = soup.get_text(
            " ",
            strip=True
        )

        return {
            "source": "TfGM",
            "status": "available",
            "checked": True,
            "summary": page_text[:2000],
        }

    except requests.RequestException as error:

        return {
            "source": "TfGM",
            "status": "unavailable",
            "checked": False,
            "summary": str(error),
        }