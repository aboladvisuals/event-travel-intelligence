async function analyzeLocally(startLocation, destination, departureTime, returnTime, eventId) {
    var event = cachedEvent || findLocalEvent(eventId) || { event_id: DEFAULT_EVENT_ID, name: "NSPPD UK Prayer Conference", venue: "Old Trafford", city: "Manchester", date: "2026-09-26", capacity: 50000, destination: destination, traffic_management: { start: "11:30", end: "21:00" }, verified_disruptions: [] };
    var eventDestination = event.destination || destination;
    var outboundRoute = await routeBetween(startLocation, eventDestination);
    var returnRoute = await routeBetween(eventDestination, startLocation);
    var outbound = applyScenario(outboundRoute.duration_minutes, departureTime, outboundScenario(departureTime, event));
    var inbound = applyScenario(returnRoute.duration_minutes, returnTime, returnScenario(returnTime, event));
    var parks = parkingSitesForEvent(event);
    var parking = [];
    for (var i = 0; i < parks.length; i++) {
        try {
            var parkRoute = await routeBetween(startLocation, parks[i].location);
            parking.push({ name: parks[i].name, location: parks[i].location, distance_miles: parkRoute.distance_miles, drive_minutes: parkRoute.duration_minutes, transfer_minutes: parks[i].transfer_minutes, total_access_minutes: parkRoute.duration_minutes + parks[i].transfer_minutes, availability: "Unknown / No live occupancy feed" });
        } catch (parkError) {
            parking.push({ name: parks[i].name, location: parks[i].location, distance_miles: null, drive_minutes: null, transfer_minutes: parks[i].transfer_minutes, total_access_minutes: null, availability: "Unknown / No live occupancy feed" });
        }
    }
    return {
        event: event,
        request: { event_id: event.event_id || eventId, start_location: startLocation, resolved_start: outboundRoute.start.display_name, departure_time: departureTime, return_time: returnTime },
        estimate_disclaimer: "Journey times are event-adjusted estimates based on a normal OSRM driving time, an event timing factor and additional event-related delay. They are not measured live traffic speeds.",
        outbound: Object.assign({ distance_miles: outboundRoute.distance_miles }, outbound),
        return: Object.assign({ distance_miles: returnRoute.distance_miles }, inbound),
        crowd: crowdRiskFromEvent(event, departureTime),
        parking: parking,
        road_conditions: { source: "TfGM", status: "configured records", note: "Verified disruption records are listed separately from modelled journey estimates." }
    };
}

function displayResults(data) {
    var outbound = data.outbound || {};
    var returnJourney = data["return"] || {};
    var crowd = data.crowd || {};
    if (data.event) { cachedEvent = data.event; renderEvent(data.event); }
    displayDisruptions((data.event && (data.event.verified_disruptions || data.event.disruptions)) || []);
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

function row(label, value) { return '<div class="detail-row"><span class="detail-label">' + label + '</span><strong>' + value + '</strong></div>'; }
function note(text) { return '<p class="note">' + escapeHtml(text) + '</p>'; }
function formatValue(value, unit) { return (value === null || value === undefined) ? "Unavailable" : value + " " + unit; }

function displayParking(parkingOptions) {
    var container = document.getElementById("parkingDetails");
    if (!parkingOptions || !parkingOptions.length) { container.innerHTML = "<p>No parking options available.</p>"; return; }
    container.innerHTML = note("Parking availability is currently not live occupancy data. Figures below are drive + transfer estimates only.") + parkingOptions.map(function (option) {
        var distance = option.distance_miles != null ? option.distance_miles + " miles" : "Unavailable";
        return '<div class="parking-option"><h4>' + escapeHtml(option.name) + '</h4>' +
            row("Location", escapeHtml(option.location || "-")) +
            row("Driving distance", distance) +
            row("Driving time", formatValue(option.drive_minutes, "min")) +
            row("Transfer time", formatValue(option.transfer_minutes, "min")) +
            row("Estimated total journey time", formatValue(option.total_access_minutes, "min")) +
            row("Availability", escapeHtml(option.availability || "Unknown / No live occupancy feed")) + '</div>';
    }).join("");
}

function displayTransport(roadConditions) {
    var container = document.getElementById("transportDetails");
    if (!container) return;
    if (!roadConditions) { container.innerHTML = "<p>No additional transport information is available.</p>"; return; }
    container.innerHTML = row("Source", escapeHtml(roadConditions.source || "TfGM")) + row("Feed status", escapeHtml(roadConditions.status || "unknown")) + note(roadConditions.note || "Verified disruption records are listed separately from modelled journey estimates.");
}

function displayDisruptions(disruptions) {
    var container = document.getElementById("disruptionDetails");
    if (!container) return;
    if (!disruptions || !disruptions.length) { container.innerHTML = "<p>No verified disruptions currently configured.</p>"; return; }
    container.innerHTML = disruptions.map(function (item) {
        return '<div class="parking-option"><h4>' + escapeHtml(item.title) + '</h4>' +
            row("Type", escapeHtml(item.type || "-")) +
            row("Period", escapeHtml((item.start || "-") + " -> " + (item.end || "-"))) +
            row("Impact", escapeHtml(item.impact || "-")) +
            row("Source", escapeHtml(item.source || "TfGM")) +
            note("Verified disruption information. This is separate from modelled / event-adjusted travel estimates.") + '</div>';
    }).join("");
}

function escapeHtml(value) {
    var el = document.createElement("div");
    el.textContent = String(value == null ? "" : value);
    return el.innerHTML;
}
