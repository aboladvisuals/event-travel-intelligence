from datetime import datetime, timedelta

from backend.event_config import EVENT


def get_outbound_scenario(departure_time):
    """
    Estimate outbound journey conditions using the configured event timing.
    """

    minutes = departure_time.hour * 60 + departure_time.minute

    traffic_start = (
        int(EVENT["traffic_management"]["start"][:2]) * 60
        + int(EVENT["traffic_management"]["start"][3:])
    )

    if minutes < 9 * 60:
        return {
            "factor": 1.00,
            "extra_delay": 0,
            "risk": "LOW",
            "label": "Normal / early departure",
        }

    if minutes < traffic_start:
        return {
            "factor": 1.15,
            "extra_delay": 0,
            "risk": "MODERATE",
            "label": "Event build-up",
        }

    if minutes < 20 * 60:
        return {
            "factor": 1.35,
            "extra_delay": 0,
            "risk": "HIGH",
            "label": "Main event period",
        }

    return {
        "factor": 1.25,
        "extra_delay": 0,
        "risk": "HIGH",
        "label": "Event dispersal",
    }


def get_return_scenario(return_time):
    """
    Estimate return journey conditions after the event.
    """

    minutes = return_time.hour * 60 + return_time.minute

    if minutes < 20 * 60:
        return {
            "factor": 1.35,
            "extra_delay": 50,
            "risk": "HIGH",
            "label": "Event still active",
        }

    if minutes < 21 * 60:
        return {
            "factor": 1.50,
            "extra_delay": 60,
            "risk": "VERY HIGH",
            "label": "Peak event dispersal",
        }

    if minutes < 22 * 60:
        return {
            "factor": 1.35,
            "extra_delay": 50,
            "risk": "HIGH",
            "label": "Heavy post-event traffic",
        }

    if minutes < 23 * 60:
        return {
            "factor": 1.20,
            "extra_delay": 30,
            "risk": "MODERATE",
            "label": "Traffic beginning to ease",
        }

    return {
        "factor": 1.05,
        "extra_delay": 10,
        "risk": "LOW",
        "label": "Late-night traffic",
    }


def format_arrival(departure_time, estimated_minutes):
    arrival_time = departure_time + timedelta(minutes=estimated_minutes)
    clock = arrival_time.strftime("%H:%M")
    days = (
        arrival_time.date() - departure_time.date()
    ).days
    if days <= 0:
        return clock
    if days == 1:
        return f"{clock} (+1 day)"
    return f"{clock} (+{days} days)"


def calculate_journey(
    normal_minutes,
    departure_time,
    direction="outbound",
):
    """
    Convert a normal routing time into an event-adjusted estimate.
    """

    if direction == "outbound":
        scenario = get_outbound_scenario(departure_time)
    else:
        scenario = get_return_scenario(departure_time)

    estimated_minutes = round(
        normal_minutes * scenario["factor"] + scenario["extra_delay"]
    )

    return {
        "normal_minutes": normal_minutes,
        "estimated_minutes": estimated_minutes,
        "factor": scenario["factor"],
        "extra_delay": scenario["extra_delay"],
        "risk": scenario["risk"],
        "label": scenario["label"],
        "departure_time": departure_time.strftime("%H:%M"),
        "arrival_time": format_arrival(departure_time, estimated_minutes),
    }


def calculate_crowd_risk(event_capacity, departure_time):
    """
    Estimate crowd/congestion risk around the event.
    """

    minutes = departure_time.hour * 60 + departure_time.minute

    score = 0
    reasons = []

    if event_capacity >= 40000:
        score += 3
        reasons.append("Large event capacity")

    if 11 * 60 + 30 <= minutes <= 21 * 60:
        score += 3
        reasons.append("Main event traffic-management period")

    elif 9 * 60 <= minutes < 11 * 60 + 30:
        score += 2
        reasons.append("Event build-up period")

    else:
        reasons.append("Outside main event traffic-management period")

    if score >= 6:
        level = "VERY HIGH"
    elif score >= 4:
        level = "HIGH"
    elif score >= 2:
        level = "MODERATE"
    else:
        level = "LOW"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
    }
