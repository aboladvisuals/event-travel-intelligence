import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta


# ============================================================
# OLD TRAFFORD TRAVEL PREDICTOR
# NSPPD UK PRAYER CONFERENCE
# 26 SEPTEMBER 2026
# ============================================================


# ------------------------------------------------------------
# 1. GEOCODING
# ------------------------------------------------------------

def get_coordinates(location):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": location,
        "format": "json",
        "limit": 1
    }

    response = requests.get(
        url,
        params=params,
        headers={
            "User-Agent": "OldTraffordTravelPredictor/1.0"
        },
        timeout=10
    )

    results = response.json()

    if not results:
        return None

    return (
        float(results[0]["lon"]),
        float(results[0]["lat"])
    )


# ------------------------------------------------------------
# 2. ROUTING
# ------------------------------------------------------------

def get_route(start, destination):

    url = (
        "https://router.project-osrm.org/"
        "route/v1/driving/"
        f"{start[0]},{start[1]};"
        f"{destination[0]},{destination[1]}"
    )

    params = {
        "overview": "false"
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    data = response.json()

    if data["code"] != "Ok":
        return None

    route = data["routes"][0]

    distance_miles = route["distance"] / 1609.34
    duration_minutes = route["duration"] / 60

    return distance_miles, duration_minutes


# ------------------------------------------------------------
# 3. LIVE TFGM EVENT INFORMATION
# ------------------------------------------------------------

def get_tfgm_event_info():

    url = "https://tfgm.com/getting-to-old-trafford"

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": "OldTraffordTravelPredictor/1.0"
            },
            timeout=10
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

        if "NSPPD United Kingdom Prayer Conference" in page_text:

            return {
                "event": "NSPPD United Kingdom Prayer Conference 2026",
                "date": "26 September 2026",
                "capacity": 50000,
                "source": "TfGM",
                "status": "Confirmed"
            }

        return None

    except requests.RequestException as error:

        print(
            f"Could not retrieve TfGM information: {error}"
        )

        return None


# ------------------------------------------------------------
# 4. CROWD / CONGESTION RISK
# ------------------------------------------------------------

def calculate_crowd_risk(
    event_info,
    departure_time
):

    score = 0
    reasons = []

    minutes = (
        departure_time.hour * 60
        + departure_time.minute
    )

    if event_info and event_info["capacity"] >= 40000:

        score += 3

        reasons.append(
            "Very large event capacity"
        )

    if 11 * 60 + 30 <= minutes <= 21 * 60:

        score += 3

        reasons.append(
            "TfGM event traffic-management window"
        )

    elif 9 * 60 <= minutes < 11 * 60 + 30:

        score += 2

        reasons.append(
            "Expected event build-up period"
        )

    else:

        reasons.append(
            "Outside main traffic-management window"
        )

    if score >= 6:

        level = "🔴 VERY HIGH"

    elif score >= 4:

        level = "🟠 HIGH"

    elif score >= 2:

        level = "🟡 MODERATE"

    else:

        level = "🟢 LOW"

    return level, score, reasons


# ------------------------------------------------------------
# 5. TRAFFIC SCENARIO
# ------------------------------------------------------------

def get_outbound_scenario(minutes):

    if minutes < 9 * 60:

        return 1.00, "Normal / early departure"

    elif minutes < 11 * 60 + 30:

        return 1.15, "Event build-up"

    elif minutes <= 20 * 60:

        return 1.35, "Main event period"

    else:

        return 1.25, "Event dispersal"


# ------------------------------------------------------------
# 6. RETURN JOURNEY SCENARIO
# ------------------------------------------------------------

def get_return_scenario(minutes):

    """
    Estimate return traffic after leaving Old Trafford.

    20:00–21:00:
    Main event dispersal.

    21:00–22:00:
    Heavy post-event traffic.

    After 22:00:
    Traffic begins to ease.

    These are modelling scenarios, not live traffic measurements.
    """

    if minutes < 20 * 60:

        factor = 1.35
        extra_delay = 50
        scenario = "Event still active"

    elif minutes <= 21 * 60:

        factor = 1.50
        extra_delay = 60
        scenario = "Peak event dispersal"

    elif minutes <= 22 * 60:

        factor = 1.35
        extra_delay = 50
        scenario = "Heavy post-event traffic"

    elif minutes <= 23 * 60:

        factor = 1.20
        extra_delay = 30
        scenario = "Traffic beginning to ease"

    else:

        factor = 1.05
        extra_delay = 10
        scenario = "Late-night traffic"

    return factor, extra_delay, scenario


# ============================================================
# MAIN PROGRAM
# ============================================================


print()
print("=" * 60)
print("        OLD TRAFFORD TRAVEL PREDICTOR")
print("=" * 60)


# ------------------------------------------------------------
# 7. OLD TRAFFORD COORDINATES
# ------------------------------------------------------------

old_trafford = get_coordinates(
    "Old Trafford, Manchester, UK"
)

if old_trafford is None:

    print("Could not locate Old Trafford.")
    exit()


# ------------------------------------------------------------
# 8. USER STARTING LOCATION
# ------------------------------------------------------------

location = input(
    "\nEnter your starting location: "
)

start = get_coordinates(location)

if start is None:

    print("Location not found.")
    exit()


# ------------------------------------------------------------
# 9. OUTBOUND ROUTE
# ------------------------------------------------------------

route = get_route(
    start,
    old_trafford
)

if route is None:

    print("Could not calculate outbound route.")
    exit()


distance, normal_time = route


print()
print("OUTBOUND JOURNEY")
print("-" * 35)

print(
    f"Starting location: {location}"
)

print(
    f"Distance: {distance:.1f} miles"
)

print(
    f"Normal driving time: "
    f"{normal_time:.0f} minutes"
)


# ------------------------------------------------------------
# 10. DEPARTURE TIME
# ------------------------------------------------------------

departure_input = input(
    "\nWhat time are you planning to leave? (HH:MM): "
)

try:

    departure_time = datetime.strptime(
        departure_input,
        "%H:%M"
    )

except ValueError:

    print(
        "Invalid time. Please use HH:MM."
    )

    exit()


departure_minutes = (
    departure_time.hour * 60
    + departure_time.minute
)


# ------------------------------------------------------------
# 11. OUTBOUND TRAFFIC
# ------------------------------------------------------------

traffic_factor, scenario = get_outbound_scenario(
    departure_minutes
)

estimated_outbound_time = (
    normal_time * traffic_factor
)

normal_arrival = (
    departure_time
    + timedelta(minutes=normal_time)
)

estimated_arrival = (
    departure_time
    + timedelta(
        minutes=estimated_outbound_time
    )
)


print()
print("TODAY'S JOURNEY ANALYSIS")
print("-" * 35)

print(
    f"Departure: "
    f"{departure_time.strftime('%H:%M')}"
)

print(
    f"Normal arrival: "
    f"{normal_arrival.strftime('%H:%M')}"
)

print(
    f"Estimated arrival: "
    f"{estimated_arrival.strftime('%H:%M')}"
)

print(
    f"\nTraffic scenario: "
    f"{scenario}"
)

print(
    f"Traffic factor: "
    f"{traffic_factor:.2f}x"
)

print(
    f"\nNormal journey: "
    f"{normal_time:.0f} minutes"
)

print(
    f"Estimated journey: "
    f"{estimated_outbound_time:.0f} minutes"
)


# ------------------------------------------------------------
# 12. EVENT POSITION AT ARRIVAL
# ------------------------------------------------------------

arrival_total_minutes = (
    departure_minutes
    + estimated_outbound_time
)


if arrival_total_minutes < 10 * 60:

    arrival_position = (
        "Before check-in period"
    )

elif arrival_total_minutes < 12 * 60:

    arrival_position = (
        "Check-in / arrival period"
    )

elif arrival_total_minutes <= 20 * 60:

    arrival_position = (
        "During main event"
    )

else:

    arrival_position = (
        "After main event"
    )


print(
    f"Arrival position: "
    f"{arrival_position}"
)


# ------------------------------------------------------------
# 13. PARK & RIDE
# ------------------------------------------------------------

park_and_ride = [

    {
        "name": "Ladywell Park & Ride",
        "location": "Ladywell, Manchester, UK",
        "transfer_minutes": 25
    },

    {
        "name": "Parkway Park & Ride",
        "location": "Parkway, Manchester, UK",
        "transfer_minutes": 25
    },

    {
        "name": "Sale Water Park Park & Ride",
        "location": "Sale Water Park, Manchester, UK",
        "transfer_minutes": 20
    }

]


print()
print("PARK & RIDE ACCESS COMPARISON")
print("-" * 40)


for option in park_and_ride:

    coordinates = get_coordinates(
        option["location"]
    )

    if coordinates is None:

        print(
            f"\n{option['name']}: "
            "location not found"
        )

        continue


    route_pr = get_route(
        start,
        coordinates
    )

    if route_pr is None:

        print(
            f"\n{option['name']}: "
            "route unavailable"
        )

        continue


    distance_pr, driving_time_pr = route_pr

    total_access_time = (
        driving_time_pr
        + option["transfer_minutes"]
    )


    print()
    print(option["name"])

    print(
        f"Drive from {location}: "
        f"{driving_time_pr:.0f} min"
    )

    print(
        f"Estimated transfer: "
        f"{option['transfer_minutes']} min"
    )

    print(
        f"Total access time: "
        f"{total_access_time:.0f} min"
    )


# ------------------------------------------------------------
# 14. PARKING INTELLIGENCE
# ------------------------------------------------------------

parking_options = [

    {
        "name": "Ladywell Park & Ride",
        "type": "Park & Ride",
        "area": "Eccles",
        "availability": "Unknown",
        "live_spaces": None
    },

    {
        "name": "Parkway Park & Ride",
        "type": "Park & Ride",
        "area": "Davyhulme",
        "availability": "Unknown",
        "live_spaces": None
    },

    {
        "name": "Sale Water Park Park & Ride",
        "type": "Park & Ride",
        "area": "Sale",
        "availability": "Unknown",
        "live_spaces": None
    }

]


print()
print("PARKING INTELLIGENCE")
print("-" * 35)


for parking in parking_options:

    print()
    print(parking["name"])

    print(
        f"Type: {parking['type']}"
    )

    print(
        f"Area: {parking['area']}"
    )

    print(
        "Live spaces: "
        "Not publicly available"
    )

    print(
        f"Availability status: "
        f"{parking['availability']}"
    )


# ------------------------------------------------------------
# 15. LIVE EVENT INFORMATION
# ------------------------------------------------------------

event_info = get_tfgm_event_info()


print()
print("LIVE EVENT INFORMATION")
print("-" * 35)


if event_info:

    print(
        f"Event: "
        f"{event_info['event']}"
    )

    print(
        f"Date: "
        f"{event_info['date']}"
    )

    print(
        f"Capacity: "
        f"{event_info['capacity']:,}"
    )

    print(
        f"Source: "
        f"{event_info['source']}"
    )

    print(
        f"Status: "
        f"{event_info['status']}"
    )

else:

    print(
        "Could not retrieve current "
        "event information."
    )


# ------------------------------------------------------------
# 16. CROWD / CONGESTION RISK
# ------------------------------------------------------------

if event_info:

    crowd_level, crowd_score, crowd_reasons = (
        calculate_crowd_risk(
            event_info,
            departure_time
        )
    )

    print()
    print("CROWD / CONGESTION RISK")
    print("-" * 35)

    print(
        f"Risk level: "
        f"{crowd_level}"
    )

    print(
        f"Risk score: "
        f"{crowd_score}/6"
    )

    print()
    print("Factors:")

    for reason in crowd_reasons:

        print(
            f"• {reason}"
        )


# ------------------------------------------------------------
# 17. DEPARTURE TIME SCENARIO ANALYSIS
# ------------------------------------------------------------

print()
print("DEPARTURE TIME SCENARIO ANALYSIS")
print("-" * 75)

print(
    f"{'Leave':<8}"
    f"{'Scenario':<28}"
    f"{'Factor':<10}"
    f"{'Journey':<12}"
    f"{'Risk'}"
)

print("-" * 75)


for hour in range(6, 23):

    test_time = datetime.strptime(
        f"{hour:02d}:00",
        "%H:%M"
    )

    test_minutes = (
        test_time.hour * 60
        + test_time.minute
    )

    factor, test_scenario = (
        get_outbound_scenario(
            test_minutes
        )
    )

    estimated_minutes = (
        normal_time * factor
    )


    if test_minutes < 9 * 60:

        risk = "LOW"

    elif test_minutes < 11 * 60 + 30:

        risk = "MODERATE"

    else:

        risk = "HIGH"


    print(
        f"{test_time.strftime('%H:%M'):<8}"
        f"{test_scenario:<28}"
        f"{factor:<10.2f}"
        f"{estimated_minutes:<12.0f}"
        f"{risk}"
    )


# ------------------------------------------------------------
# 18. ARRIVAL TIME ANALYSIS
# ------------------------------------------------------------

print()
print("ARRIVAL TIME ANALYSIS")
print("-" * 80)

print(
    f"{'Leave':<8}"
    f"{'Arrive':<10}"
    f"{'Journey':<12}"
    f"{'Event Position':<30}"
    f"{'Risk'}"
)

print("-" * 80)


for hour in range(6, 23):

    test_time = datetime.strptime(
        f"{hour:02d}:00",
        "%H:%M"
    )

    test_minutes = (
        test_time.hour * 60
        + test_time.minute
    )

    factor, _ = get_outbound_scenario(
        test_minutes
    )

    journey_minutes = (
        normal_time * factor
    )

    arrival_time = (
        test_time
        + timedelta(
            minutes=journey_minutes
        )
    )

    arrival_total_minutes = (
        test_minutes
        + journey_minutes
    )


    if arrival_total_minutes < 10 * 60:

        event_position = (
            "Before check-in period"
        )

        risk = "LOW"


    elif arrival_total_minutes < 12 * 60:

        event_position = (
            "Check-in / arrival period"
        )

        risk = "MODERATE"


    elif arrival_total_minutes <= 20 * 60:

        event_position = (
            "During main event"
        )

        risk = "HIGH"


    else:

        event_position = (
            "After main event"
        )

        risk = "HIGH"


    print(
        f"{test_time.strftime('%H:%M'):<8}"
        f"{arrival_time.strftime('%H:%M'):<10}"
        f"{journey_minutes:<12.0f}"
        f"{event_position:<30}"
        f"{risk}"
    )


# ============================================================
# 19. RETURN JOURNEY
# ============================================================

print()
print("=" * 60)
print("              RETURN JOURNEY MODEL")
print("=" * 60)


return_input = input(
    "\nWhat time will you leave Old Trafford? (HH:MM): "
)


try:

    return_departure = datetime.strptime(
        return_input,
        "%H:%M"
    )

except ValueError:

    print(
        "Invalid time. Please use HH:MM."
    )

    exit()


return_minutes = (
    return_departure.hour * 60
    + return_departure.minute
)


return_factor, return_extra_delay, return_scenario = (
    get_return_scenario(
        return_minutes
    )
)


estimated_return_time = (
    normal_time * return_factor
    + return_extra_delay
)


return_arrival = (
    return_departure
    + timedelta(
        minutes=estimated_return_time
    )
)


print()
print("RETURN JOURNEY ANALYSIS")
print("-" * 40)

print(
    f"Leaving Old Trafford: "
    f"{return_departure.strftime('%H:%M')}"
)

print(
    f"Destination: "
    f"{location}"
)

print(
    f"Normal return journey: "
    f"{normal_time:.0f} minutes"
)

print(
    f"Return traffic scenario: "
    f"{return_scenario}"
)

print(
    f"Return traffic factor: "
    f"{return_factor:.2f}x"
)

print(
    f"Additional event delay: "
    f"{return_extra_delay} minutes"
)

print(
    f"Estimated return journey: "
    f"{estimated_return_time:.0f} minutes"
)

print(
    f"Estimated arrival back: "
    f"{return_arrival.strftime('%H:%M')}"
)


# ------------------------------------------------------------
# 20. RETURN RISK
# ------------------------------------------------------------

if return_minutes <= 21 * 60:

    return_risk = "🔴 VERY HIGH"

elif return_minutes <= 22 * 60:

    return_risk = "🟠 HIGH"

elif return_minutes <= 23 * 60:

    return_risk = "🟡 MODERATE"

else:

    return_risk = "🟢 LOWER"


print(
    f"Return congestion risk: "
    f"{return_risk}"
)


# ------------------------------------------------------------
# 21. FINAL SUMMARY
# ------------------------------------------------------------

print()
print("=" * 60)
print("                    SUMMARY")
print("=" * 60)

print(
    f"Outbound: "
    f"{location} → Old Trafford"
)

print(
    f"Outbound distance: "
    f"{distance:.1f} miles"
)

print(
    f"Outbound estimate: "
    f"{estimated_outbound_time:.0f} minutes"
)

print(
    f"Arrival estimate: "
    f"{estimated_arrival.strftime('%H:%M')}"
)

print(
    f"Return estimate: "
    f"{estimated_return_time:.0f} minutes"
)

print(
    f"Return arrival: "
    f"{return_arrival.strftime('%H:%M')}"
)

print(
    f"Return risk: "
    f"{return_risk}"
)

print()
print(
    "NOTE: Traffic multipliers are scenario assumptions, "
    "not live traffic measurements."
)
