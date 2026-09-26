function looksExplicitlyInternational(location) {
    var compact = String(location || "").toLowerCase();
    var ukHints = ["united kingdom", "great britain", "northern ireland", "england", "scotland", "wales", "u.k.", " uk", "uk ", "gb"];
    var i;
    for (i = 0; i < ukHints.length; i++) if (compact.indexOf(ukHints[i]) !== -1) return false;
    var internationalHints = ["united states", "usa", "u.s.a", "america", "canada", "australia", "virginia", "california", "texas", "new york", "florida"];
    for (i = 0; i < internationalHints.length; i++) if (compact.indexOf(internationalHints[i]) !== -1) return true;
    return false;
}

var UK_QUERY_ALIASES = { "southhampton": "Southampton" };

function geocodeVariants(location) {
    var variants = [location];
    var compact = String(location || "").trim().toLowerCase();
    var alias = UK_QUERY_ALIASES[compact];
    if (alias) variants.push(alias);
    if (compact.indexOf("uk") === -1 && compact.indexOf("united kingdom") === -1 && compact.indexOf("england") === -1) {
        variants.push(location + ", UK");
        if (alias) variants.push(alias + ", UK");
    }
    return variants;
}

async function geocode(location) {
    async function search(query, extraQuery) {
        var response = await fetchJson("https://nominatim.openstreetmap.org/search?format=json&limit=5&q=" + encodeURIComponent(query) + extraQuery, {}, 20000);
        if (!response.ok) throw new Error("Could not geocode " + location);
        return response.json();
    }
    function isUkResult(item) {
        var name = String((item && item.display_name) || "").toLowerCase();
        return name.indexOf("united kingdom") !== -1 || name.indexOf("england") !== -1 || name.indexOf("scotland") !== -1 || name.indexOf("wales") !== -1 || name.indexOf("northern ireland") !== -1;
    }
    var results = [];
    var variants = geocodeVariants(location);
    var i;
    if (!looksExplicitlyInternational(location)) {
        for (i = 0; i < variants.length; i++) {
            results = await search(variants[i], "&countrycodes=gb");
            if (results && results.length) break;
        }
    }
    if (!results || !results.length) {
        results = await search(location, "");
        var ukMatches = (results || []).filter(isUkResult);
        if (ukMatches.length) results = ukMatches;
    }
    if (!results || !results.length) throw new Error("Location not found: " + location);
    return { latitude: parseFloat(results[0].lat), longitude: parseFloat(results[0].lon), display_name: results[0].display_name };
}

async function routeBetween(start, dest) {
    var startCoords = await geocode(start);
    var destCoords = await geocode(dest);
    var response = await fetchJson("https://router.project-osrm.org/route/v1/driving/" + startCoords.longitude + "," + startCoords.latitude + ";" + destCoords.longitude + "," + destCoords.latitude + "?overview=false", {}, 20000);
    if (!response.ok) throw new Error("No driving route found.");
    var payload = await response.json();
    if (!payload.routes || !payload.routes.length) throw new Error("No driving route found.");
    return {
        distance_miles: Math.round((payload.routes[0].distance / 1609.344) * 10) / 10,
        duration_minutes: Math.round(payload.routes[0].duration / 60),
        start: startCoords,
        destination: destCoords
    };
}

function minutesOf(hhmm) {
    var parts = String(hhmm || "00:00").split(":");
    return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
}

function formatArrivalClock(hhmm, extraMinutes) {
    var total = minutesOf(hhmm) + Number(extraMinutes || 0);
    if (!isFinite(total)) return hhmm || "-";
    var days = Math.floor(total / (24 * 60));
    var remain = total % (24 * 60);
    var clock = String(Math.floor(remain / 60)).padStart(2, "0") + ":" + String(remain % 60).padStart(2, "0");
    if (days <= 0) return clock;
    return days === 1 ? clock + " (+1 day)" : clock + " (+" + days + " days)";
}

function formatArrivalValue(journey) {
    if (!journey) return "-";
    if (journey.departure_time != null && journey.estimated_minutes != null) return formatArrivalClock(journey.departure_time, journey.estimated_minutes);
    return journey.arrival_time || "-";
}

function eventWindows(event) {
    event = event || {};
    var traffic = event.traffic_management || {};
    var trafficStart = minutesOf(event.traffic_management_start || traffic.start || "11:30");
    var trafficEnd = minutesOf(event.traffic_management_end || traffic.end || "21:00");
    var startTime = event.start_time ? minutesOf(event.start_time) : trafficStart;
    var earlyCutoff = Math.min(startTime, trafficStart);
    if (earlyCutoff > 9 * 60) earlyCutoff = Math.max(9 * 60, trafficStart - 150);
    return { earlyCutoff: earlyCutoff, trafficStart: trafficStart, mainUntil: Math.max(trafficEnd - 60, trafficStart), trafficEnd: trafficEnd };
}

function outboundScenario(departureTime, event) {
    var minutes = minutesOf(departureTime);
    var windows = eventWindows(event);
    if (minutes < windows.earlyCutoff) return { factor: 1.00, extra_delay: 0, risk: "LOW", label: "Normal / early departure" };
    if (minutes < windows.trafficStart) return { factor: 1.15, extra_delay: 0, risk: "MODERATE", label: "Event build-up" };
    if (minutes < windows.mainUntil) return { factor: 1.35, extra_delay: 0, risk: "HIGH", label: "Main event period" };
    return { factor: 1.25, extra_delay: 0, risk: "HIGH", label: "Event dispersal" };
}

function returnScenario(returnTime, event) {
    var minutes = minutesOf(returnTime);
    var trafficEnd = eventWindows(event).trafficEnd;
    if (minutes < trafficEnd - 60) return { factor: 1.35, extra_delay: 50, risk: "HIGH", label: "Event still active" };
    if (minutes < trafficEnd) return { factor: 1.50, extra_delay: 60, risk: "VERY HIGH", label: "Peak event dispersal" };
    if (minutes < trafficEnd + 60) return { factor: 1.35, extra_delay: 50, risk: "HIGH", label: "Heavy post-event traffic" };
    if (minutes < trafficEnd + 120) return { factor: 1.20, extra_delay: 30, risk: "MODERATE", label: "Traffic beginning to ease" };
    return { factor: 1.05, extra_delay: 10, risk: "LOW", label: "Late-night traffic" };
}

function applyScenario(normalMinutes, time, scenario) {
    var estimated = Math.round(normalMinutes * scenario.factor + scenario.extra_delay);
    return { normal_minutes: normalMinutes, estimated_minutes: estimated, factor: scenario.factor, extra_delay: scenario.extra_delay, risk: scenario.risk, label: scenario.label, departure_time: time, arrival_time: formatArrivalClock(time, estimated) };
}

function crowdRiskFromEvent(event, departureTime) {
    var minutes = minutesOf(departureTime);
    var windows = eventWindows(event);
    var capacity = (event && event.capacity) || 0;
    var score = 0;
    var reasons = [];
    if (capacity >= 40000) { score += 3; reasons.push("Large event capacity"); }
    if (minutes >= windows.trafficStart && minutes <= windows.trafficEnd) { score += 3; reasons.push("Main event traffic-management period"); }
    else if (minutes >= windows.earlyCutoff && minutes < windows.trafficStart) { score += 2; reasons.push("Event build-up period"); }
    else { reasons.push("Outside main event traffic-management period"); }
    return { score: score, level: score >= 6 ? "VERY HIGH" : score >= 4 ? "HIGH" : score >= 2 ? "MODERATE" : "LOW", reasons: reasons };
}

function parkingSitesForEvent(event) {
    if (event && event.parking_options && event.parking_options.length) return event.parking_options;
    if (event && event.parking) return Object.keys(event.parking).map(function (key) { return event.parking[key]; });
    return [
        { name: "Ladywell Park & Ride", location: "Ladywell, Manchester, UK", transfer_minutes: 25 },
        { name: "Parkway Park & Ride", location: "Parkway, Manchester, UK", transfer_minutes: 25 },
        { name: "Sale Water Park Park & Ride", location: "Sale Water Park, Manchester, UK", transfer_minutes: 20 }
    ];
}
