document.addEventListener("DOMContentLoaded", function () {
    loadEvent();
});

var API_URL = "https://event-travel-intelligence.onrender.com";
var analyzeButton = document.getElementById("analyzeButton");
var statusElement = document.getElementById("status");
var resultsSection = document.getElementById("results");
var cachedEvent = null;

if (analyzeButton) {
    analyzeButton.addEventListener("click", analyzeJourney);
}

async function fetchJson(url, options, timeoutMs) {
    options = options || {};
    timeoutMs = timeoutMs || 20000;
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs);
    try {
        return await fetch(url, Object.assign({}, options, { signal: controller.signal }));
    } finally {
        clearTimeout(timer);
    }
}

async function loadEvent() {
    try {
        var response = await fetchJson(API_URL + "/event", {}, 12000);
        if (!response.ok) throw new Error("API event request failed");
        cachedEvent = await response.json();
        renderEvent(cachedEvent);
        displayDisruptions(cachedEvent.verified_disruptions || []);
        return;
    } catch (apiError) {
        try {
            var local = await fetchJson("event.json", {}, 8000);
            if (!local.ok) throw new Error("Local event file missing");
            cachedEvent = await local.json();
            renderEvent(cachedEvent);
            displayDisruptions(cachedEvent.verified_disruptions || []);
            if (statusElement) {
                statusElement.textContent = "Event loaded. Analyze Journey uses the public API when CORS is available.";
            }
            return;
        } catch (localError) {
            document.getElementById("eventName").textContent = "Event Travel Intelligence";
            document.getElementById("destination").placeholder = "Old Trafford, Manchester, UK";
            document.getElementById("destination").value = "Old Trafford, Manchester, UK";
            if (statusElement) statusElement.textContent = "Could not load event configuration.";
        }
    }
}

function renderEvent(event) {
    var eventName = document.getElementById("eventName");
    var eventMeta = document.getElementById("eventMeta");
    var destinationInput = document.getElementById("destination");
    if (eventName) eventName.textContent = event.name || "Event Travel Intelligence";
    if (destinationInput) {
        destinationInput.value = event.destination || "Old Trafford, Manchester, UK";
        destinationInput.placeholder = event.destination || "Event destination";
    }
    if (eventMeta) {
        var parts = [
            event.venue,
            event.city,
            formatDate(event.date),
            event.capacity ? ("Capacity " + Number(event.capacity).toLocaleString("en-GB")) : null,
            event.traffic_management ? ("Traffic management " + event.traffic_management.start + "-" + event.traffic_management.end) : null
        ].filter(Boolean);
        eventMeta.textContent = parts.join(" | ");
    }
}

function formatDate(value) {
    if (!value) return "";
    var date = new Date(value + "T00:00:00");
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

async function analyzeJourney() {
    var startLocation = document.getElementById("startLocation").value.trim();
    var destination = document.getElementById("destination").value.trim();
    var departureTime = document.getElementById("departureTime").value;
    var returnTime = document.getElementById("returnTime").value;

    if (!startLocation || !destination || !departureTime || !returnTime) {
        statusElement.textContent = "Please complete all fields.";
        return;
    }

    analyzeButton.disabled = true;
    statusElement.textContent = "Analyzing route, event conditions and parking...";
    resultsSection.classList.add("hidden");

    try {
        var response = await fetchJson(API_URL + "/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                start_location: startLocation,
                destination: destination,
                departure_time: departureTime,
                return_time: returnTime,
                event_capacity: 50000
            })
        }, 90000);
        var data = await response.json();
        if (!response.ok) throw new Error((data && data.detail) || "Analysis failed.");
        displayResults(data);
        statusElement.textContent = "Analysis complete. Times shown are event-adjusted estimates, not live traffic speeds.";
        resultsSection.classList.remove("hidden");
    } catch (error) {
        try {
            statusElement.textContent = "Public API blocked or busy. Calculating a local event-adjusted estimate...";
            var data = await analyzeLocally(startLocation, destination, departureTime, returnTime);
            displayResults(data);
            statusElement.textContent = "Analysis complete via routing services. Times shown are event-adjusted estimates, not live traffic speeds.";
            resultsSection.classList.remove("hidden");
        } catch (localError) {
            statusElement.textContent = "Error: " + (localError.message || error.message);
        }
    } finally {
        analyzeButton.disabled = false;
    }
}

function looksExplicitlyInternational(location) {
    var compact = String(location || "").toLowerCase();
    var ukHints = ["united kingdom", "great britain", "northern ireland", "england", "scotland", "wales", "u.k.", " uk", "uk ", "gb"];
    var i;
    for (i = 0; i < ukHints.length; i++) {
        if (compact.indexOf(ukHints[i]) !== -1) return false;
    }
    var internationalHints = ["united states", "usa", "u.s.a", "u.s.", "america", "canada", "australia", "new zealand", "ireland", "france", "germany", "spain", "italy", "portugal", "netherlands", "belgium", "switzerland", "austria", "sweden", "norway", "denmark", "poland", "india", "pakistan", "nigeria", "ghana", "kenya", "south africa", "japan", "china", "singapore", "uae", "dubai", "qatar", "brazil", "mexico", "virginia", "california", "texas", "new york", "florida"];
    for (i = 0; i < internationalHints.length; i++) {
        if (compact.indexOf(internationalHints[i]) !== -1) return true;
    }
    return false;
}

async function geocode(location) {
    async function search(extraQuery) {
        var url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + encodeURIComponent(location) + extraQuery;
        var response = await fetchJson(url, {}, 20000);
        if (!response.ok) throw new Error("Could not geocode " + location);
        return response.json();
    }

    var results = [];
    if (!looksExplicitlyInternational(location)) {
        results = await search("&countrycodes=gb");
    }
    if (!results || !results.length) {
        results = await search("");
    }
    if (!results.length) throw new Error("Location not found: " + location);
    return {
        latitude: parseFloat(results[0].lat),
        longitude: parseFloat(results[0].lon),
        display_name: results[0].display_name
    };
}

async function routeBetween(start, dest) {
    var startCoords = await geocode(start);
    var destCoords = await geocode(dest);
    var url = "https://router.project-osrm.org/route/v1/driving/" +
        startCoords.longitude + "," + startCoords.latitude + ";" +
        destCoords.longitude + "," + destCoords.latitude + "?overview=false";
    var response = await fetchJson(url, {}, 20000);
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
    var hours = Math.floor(remain / 60);
    var mins = remain % 60;
    var clock = String(hours).padStart(2, "0") + ":" + String(mins).padStart(2, "0");
    if (days <= 0) return clock;
    if (days === 1) return clock + " (+1 day)";
    return clock + " (+" + days + " days)";
}

function formatArrivalValue(journey) {
    if (!journey) return "-";
    if (journey.departure_time != null && journey.estimated_minutes != null) {
        return formatArrivalClock(journey.departure_time, journey.estimated_minutes);
    }
    return journey.arrival_time || "-";
}

function outboundScenario(departureTime) {
    var minutes = minutesOf(departureTime);
    if (minutes < 9 * 60) return { factor: 1.00, extra_delay: 0, risk: "LOW", label: "Normal / early departure" };
    if (minutes < 11 * 60 + 30) return { factor: 1.15, extra_delay: 0, risk: "MODERATE", label: "Event build-up" };
    if (minutes < 20 * 60) return { factor: 1.35, extra_delay: 0, risk: "HIGH", label: "Main event period" };
    return { factor: 1.25, extra_delay: 0, risk: "HIGH", label: "Event dispersal" };
}

function returnScenario(returnTime) {
    var minutes = minutesOf(returnTime);
    if (minutes < 20 * 60) return { factor: 1.35, extra_delay: 50, risk: "HIGH", label: "Event still active" };
    if (minutes < 21 * 60) return { factor: 1.50, extra_delay: 60, risk: "VERY HIGH", label: "Peak event dispersal" };
    if (minutes < 22 * 60) return { factor: 1.35, extra_delay: 50, risk: "HIGH", label: "Heavy post-event traffic" };
    if (minutes < 23 * 60) return { factor: 1.20, extra_delay: 30, risk: "MODERATE", label: "Traffic beginning to ease" };
    return { factor: 1.05, extra_delay: 10, risk: "LOW", label: "Late-night traffic" };
}

function applyScenario(normalMinutes, time, scenario) {
    var estimated = Math.round(normalMinutes * scenario.factor + scenario.extra_delay);
    return {
        normal_minutes: normalMinutes,
        estimated_minutes: estimated,
        factor: scenario.factor,
        extra_delay: scenario.extra_delay,
        risk: scenario.risk,
        label: scenario.label,
        departure_time: time,
        arrival_time: formatArrivalClock(time, estimated)
    };
}

function crowdRisk(capacity, departureTime) {
    var minutes = minutesOf(departureTime);
    var score = 0;
    var reasons = [];
    if (capacity >= 40000) { score += 3; reasons.push("Large event capacity"); }
    if (minutes >= 11 * 60 + 30 && minutes <= 21 * 60) { score += 3; reasons.push("Main event traffic-management period"); }
    else if (minutes >= 9 * 60 && minutes < 11 * 60 + 30) { score += 2; reasons.push("Event build-up period"); }
    else { reasons.push("Outside main event traffic-management period"); }
    var level = score >= 6 ? "VERY HIGH" : score >= 4 ? "HIGH" : score >= 2 ? "MODERATE" : "LOW";
    return { score: score, level: level, reasons: reasons };
}

async function analyzeLocally(startLocation, destination, departureTime, returnTime) {
    var event = cachedEvent || { name: "NSPPD UK Prayer Conference", venue: "Old Trafford", city: "Manchester", date: "2026-09-26", capacity: 50000, destination: destination, verified_disruptions: [] };
    var outboundRoute = await routeBetween(startLocation, destination);
    var returnRoute = await routeBetween(destination, startLocation);
    var outbound = applyScenario(outboundRoute.duration_minutes, departureTime, outboundScenario(departureTime));
    var inbound = applyScenario(returnRoute.duration_minutes, returnTime, returnScenario(returnTime));
    var parks = [
        { name: "Ladywell Park & Ride", location: "Ladywell, Manchester, UK", transfer_minutes: 25 },
        { name: "Parkway Park & Ride", location: "Parkway, Manchester, UK", transfer_minutes: 25 },
        { name: "Sale Water Park Park & Ride", location: "Sale Water Park, Manchester, UK", transfer_minutes: 20 }
    ];
    var parking = [];
    for (var i = 0; i < parks.length; i++) {
        try {
            var parkRoute = await routeBetween(startLocation, parks[i].location);
            parking.push({
                name: parks[i].name,
                location: parks[i].location,
                distance_miles: parkRoute.distance_miles,
                drive_minutes: parkRoute.duration_minutes,
                transfer_minutes: parks[i].transfer_minutes,
                total_access_minutes: parkRoute.duration_minutes + parks[i].transfer_minutes,
                availability: "Unknown / No live occupancy feed"
            });
        } catch (parkError) {
            parking.push({
                name: parks[i].name,
                location: parks[i].location,
                distance_miles: null,
                drive_minutes: null,
                transfer_minutes: parks[i].transfer_minutes,
                total_access_minutes: null,
                availability: "Unknown / No live occupancy feed"
            });
        }
    }
    return {
        event: event,
        request: { start_location: startLocation, resolved_start: outboundRoute.start.display_name, departure_time: departureTime, return_time: returnTime },
        estimate_disclaimer: "Journey times are event-adjusted estimates based on a normal OSRM driving time, an event timing factor and additional event-related delay. They are not measured live traffic speeds.",
        outbound: Object.assign({ distance_miles: outboundRoute.distance_miles }, outbound),
        return: Object.assign({ distance_miles: returnRoute.distance_miles }, inbound),
        crowd: crowdRisk(event.capacity || 50000, departureTime),
        parking: parking,
        road_conditions: { source: "TfGM", status: "configured records", note: "Verified disruption records are listed separately from modelled journey estimates." }
    };
}

function displayResults(data) {
    var outbound = data.outbound || {};
    var returnJourney = data["return"] || {};
    var crowd = data.crowd || {};
    displayDisruptions((data.event && data.event.verified_disruptions) || []);
    document.getElementById("outboundDistance").textContent = outbound.distance_miles != null ? outbound.distance_miles + " miles" : "-";
    document.getElementById("outboundTime").textContent = outbound.estimated_minutes != null ? outbound.estimated_minutes + " min" : "-";
    document.getElementById("arrivalTime").textContent = formatArrivalValue(outbound);
    document.getElementById("outboundRisk").textContent = outbound.risk || "-";
    var resolvedOrigin = (data.request && (data.request.resolved_start || data.request.start_location)) || "-";
    document.getElementById("outboundDetails").innerHTML =
        row("Resolved origin", escapeHtml(resolvedOrigin)) +
        row("Normal driving time (OSRM)", formatValue(outbound.normal_minutes, "min")) +
        row("Estimated event-adjusted time", formatValue(outbound.estimated_minutes, "min")) +
        row("Traffic factor", outbound.factor != null ? outbound.factor + "x" : "-") +
        row("Additional event-related delay", formatValue(outbound.extra_delay, "min")) +
        row("Condition", escapeHtml(outbound.label || "-")) +
        note(data.estimate_disclaimer || "Journey times are event-adjusted estimates and are not measured live traffic speeds.");
    document.getElementById("crowdDetails").innerHTML =
        row("Risk level", escapeHtml(crowd.level || "-")) +
        row("Risk score", crowd.score != null ? crowd.score + "/6" : "-") +
        row("Factors", escapeHtml((crowd.reasons || []).join(", ") || "-"));
    document.getElementById("returnDetails").innerHTML =
        row("Normal driving time (OSRM)", formatValue(returnJourney.normal_minutes, "min")) +
        row("Estimated return time", formatValue(returnJourney.estimated_minutes, "min")) +
        row("Estimated arrival", escapeHtml(formatArrivalValue(returnJourney))) +
        row("Return risk", escapeHtml(returnJourney.risk || "-")) +
        row("Condition", escapeHtml(returnJourney.label || "-")) +
        note("Return times are modelled from the same event-adjustment method. They are not live measured speeds.");
    displayParking(data.parking);
    displayTransport(data.road_conditions);
}

function row(label, value) {
    return '<div class="detail-row"><span class="detail-label">' + label + '</span><strong>' + value + '</strong></div>';
}

function note(text) {
    return '<p class="note">' + escapeHtml(text) + '</p>';
}

function displayParking(parkingOptions) {
    var container = document.getElementById("parkingDetails");
    if (!parkingOptions || !parkingOptions.length) {
        container.innerHTML = "<p>No parking options available.</p>";
        return;
    }
    var cards = parkingOptions.map(function (option) {
        var distance = option.distance_miles != null ? option.distance_miles + " miles" : "Unavailable";
        return '<div class="parking-option"><h4>' + escapeHtml(option.name) + '</h4>' +
            row("Location", escapeHtml(option.location || "-")) +
            row("Driving distance", distance) +
            row("Driving time", formatValue(option.drive_minutes, "min")) +
            row("Transfer time", formatValue(option.transfer_minutes, "min")) +
            row("Estimated total journey time", formatValue(option.total_access_minutes, "min")) +
            row("Availability", escapeHtml(option.availability || "Unknown / No live occupancy feed")) +
            '</div>';
    }).join("");
    container.innerHTML = note("Parking availability is currently not live occupancy data. Figures below are drive + transfer estimates only.") + cards;
}

function displayTransport(roadConditions) {
    var container = document.getElementById("transportDetails");
    if (!container) return;
    if (!roadConditions) {
        container.innerHTML = "<p>No additional transport information is available.</p>";
        return;
    }
    container.innerHTML =
        row("Source", escapeHtml(roadConditions.source || "TfGM")) +
        row("Feed status", escapeHtml(roadConditions.status || "unknown")) +
        note(roadConditions.note || "Verified disruption records are listed separately from modelled journey estimates.");
}

function formatValue(value, unit) {
    if (value === null || value === undefined) return "Unavailable";
    return value + " " + unit;
}

function displayDisruptions(disruptions) {
    var container = document.getElementById("disruptionDetails");
    if (!container) return;
    if (!disruptions || !disruptions.length) {
        container.innerHTML = "<p>No verified disruptions currently configured.</p>";
        return;
    }
    container.innerHTML = disruptions.map(function (item) {
        return '<div class="parking-option"><h4>' + escapeHtml(item.title) + '</h4>' +
            row("Type", escapeHtml(item.type || "-")) +
            row("Period", escapeHtml((item.start || "-") + " -> " + (item.end || "-"))) +
            row("Impact", escapeHtml(item.impact || "-")) +
            row("Source", escapeHtml(item.source || "TfGM")) +
            note("Verified disruption information. This is separate from modelled / event-adjusted travel estimates.") +
            '</div>';
    }).join("");
}

function escapeHtml(value) {
    var el = document.createElement("div");
    el.textContent = String(value == null ? "" : value);
    return el.innerHTML;
}
