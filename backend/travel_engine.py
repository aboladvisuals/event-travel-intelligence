from datetime import datetime, timedelta


def _as_minutes(value, default_minutes):
    if not value:
        return default_minutes
    if isinstance(value, int):
        return value
    parts = str(value).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _event_windows(event):
    event = event or {}
    traffic = event.get("traffic_management") or {}
    traffic_start = _as_minutes(
        event.get("traffic_management_start") or traffic.get("start"),
        11 * 60 + 30,
    )
    traffic_end = _as_minutes(
        event.get("traffic_management_end") or traffic.get("end"),
        21 * 60,
    )
    start_time = _as_minutes(event.get("start_time"), traffic_start)
    early_cutoff = min(start_time, traffic_start)
    if early_cutoff > 9 * 60:
        early_cutoff = max(9 * 60, traffic_start - 150)
    main_until = max(traffic_end - 60, traffic_start)
    return {
        "early_cutoff": early_cutoff,
        "traffic_start": traffic_start,
        "main_until": main_until,
        "traffic_end": traffic_end,
    }


def get_outbound_scenario(departure_time, event=None):
    minutes = departure_time.hour * 60 + departure_time.minute
    windows = _event_windows(event)

    if minutes < windows["early_cutoff"]:
        return {
            "factor": 1.00,
            "extra_delay": 0,
            "risk": "LOW",
            "label": "Normal / early departure",
        }

    if minutes < windows["traffic_start"]:
        return {
            "factor": 1.15,
            "extra_delay": 0,
            "risk": "MODERATE",
            "label": "Event build-up",
        }

    if minutes < windows["main_until"]:
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


def get_return_scenario(return_time, event=None):
    minutes = return_time.hour * 60 + return_time.minute
    windows = _event_windows(event)
    traffic_end = windows["traffic_end"]

    if minutes < traffic_end - 60:
        return {
            "factor": 1.35,
            "extra_delay": 50,
            "risk": "HIGH",
            "label": "Event still active",
        }

    if minutes < traffic_end:
        return {
            "factor": 1.50,
            "extra_delay": 60,
            "risk": "VERY HIGH",
            "label": "Peak event dispersal",
        }

    if minutes < traffic_end + 60:
        return {
            "factor": 1.35,
            "extra_delay": 50,
            "risk": "HIGH",
            "label": "Heavy post-event traffic",
        }

    if minutes < traffic_end + 120:
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
    days = (arrival_time.date() - departure_time.date()).days
    if days <= 0:
        return clock
    if days == 1:
        return f"{clock} (+1 day)"
    return f"{clock} (+{days} days)"


def arrival_rollover_days(departure_time, estimated_minutes):
    arrival_time = departure_time + timedelta(minutes=estimated_minutes)
    return (arrival_time.date() - departure_time.date()).days


def journey_breakdown(normal_minutes, estimated_minutes, extra_delay):
    event_impact = estimated_minutes - extra_delay - normal_minutes
    return {
        "normal_minutes": normal_minutes,
        "event_impact_minutes": event_impact,
        "extra_delay_minutes": extra_delay,
        "estimated_minutes": estimated_minutes,
    }


def calculate_journey(
    normal_minutes,
    departure_time,
    direction="outbound",
    event=None,
):
    if direction == "outbound":
        scenario = get_outbound_scenario(departure_time, event)
    else:
        scenario = get_return_scenario(departure_time, event)

    estimated_minutes = round(
        normal_minutes * scenario["factor"] + scenario["extra_delay"]
    )
    breakdown = journey_breakdown(
        normal_minutes,
        estimated_minutes,
        scenario["extra_delay"],
    )
    rollover = arrival_rollover_days(departure_time, estimated_minutes)

    return {
        "normal_minutes": normal_minutes,
        "estimated_minutes": estimated_minutes,
        "factor": scenario["factor"],
        "extra_delay": scenario["extra_delay"],
        "risk": scenario["risk"],
        "label": scenario["label"],
        "departure_time": departure_time.strftime("%H:%M"),
        "arrival_time": format_arrival(departure_time, estimated_minutes),
        "arrival_days": rollover,
        "day_rollover": rollover > 0,
        "breakdown": breakdown,
    }


def calculate_crowd_risk(event_capacity, departure_time, event=None):
    minutes = departure_time.hour * 60 + departure_time.minute
    windows = _event_windows(event)

    score = 0
    reasons = []

    if event_capacity >= 40000:
        score += 3
        reasons.append("Large event capacity")

    if windows["traffic_start"] <= minutes <= windows["traffic_end"]:
        score += 3
        reasons.append("Main event traffic-management period")
    elif windows["early_cutoff"] <= minutes < windows["traffic_start"]:
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
