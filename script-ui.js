var journeyMap = null;
var journeyMapLayers = [];

async function analyzeLocally(startLocation, destination, departureTime, returnTime, eventId) {
    var event = cachedEvent || findLocalEvent(eventId) || { event_id: DEFAULT_EVENT_ID, name: "NSPPD UK Prayer Conference", venue: "Old Trafford", city: "Manchester", date: "2026-09-26", capacity: 50000, destination: destination, traffic_management: { start: "11:30", end: "21:00" }, verified_disruptions: [] };
    var eventDestination = event.destination || destination;
    var outboundBundle = await getRoutes(startLocation, eventDestination);
    var returnBundle = await getRoutes(eventDestination, startLocation);
    var liveTraffic = typeof unavailableLiveTraffic === "function" ? unavailableLiveTraffic("The local fallback cannot read a licensed live-speed feed. Live traffic is unavailable.") : { available: false, status: "unavailable", additional_minutes: null, source: "None configured", checked_at: new Date().toISOString(), note: "Live traffic is unavailable." };
    var outbound = applyScenario(outboundBundle.routes[0].duration_minutes, departureTime, outboundScenario(departureTime, event));
    if (typeof applyLiveTraffic === "function") { outbound.breakdown = applyLiveTraffic(outbound.breakdown, liveTraffic); outbound.estimated_minutes = outbound.breakdown.estimated_minutes; }
    var inbound = applyScenario(returnBundle.routes[0].duration_minutes, returnTime, returnScenario(returnTime, event));
    if (typeof applyLiveTraffic === "function") { inbound.breakdown = applyLiveTraffic(inbound.breakdown, liveTraffic); inbound.estimated_minutes = inbound.breakdown.estimated_minutes; }
    var outboundOptions = outboundBundle.routes.map(function (option) {
        var adjusted = applyScenario(option.duration_minutes, departureTime, outboundScenario(departureTime, event));
        return { id: option.id, label: option.label, distance_miles: option.distance_miles, normal_minutes: adjusted.normal_minutes, estimated_minutes: adjusted.estimated_minutes, breakdown: adjusted.breakdown, geometry: option.geometry || [] };
    });
    var returnOptions = returnBundle.routes.map(function (option) {
        var adjusted = applyScenario(option.duration_minutes, returnTime, returnScenario(returnTime, event));
        return { id: option.id, label: option.label, distance_miles: option.distance_miles, normal_minutes: adjusted.normal_minutes, estimated_minutes: adjusted.estimated_minutes, breakdown: adjusted.breakdown, geometry: option.geometry || [] };
    });
    var parks = parkingSitesForEvent(event);
    var parking = [];
    for (var i = 0; i < parks.length; i++) {
        try {
            var parkRoute = await routeBetween(startLocation, parks[i].location);
            parking.push({ name: parks[i].name, location: parks[i].location, distance_miles: parkRoute.distance_miles, drive_minutes: parkRoute.duration_minutes, transfer_minutes: parks[i].transfer_minutes, total_access_minutes: parkRoute.duration_minutes + parks[i].transfer_minutes, availability: "Unknown / No live occupancy feed", latitude: parkRoute.destination.latitude, longitude: parkRoute.destination.longitude });
        } catch (parkError) {
            parking.push({ name: parks[i].name, location: parks[i].location, distance_miles: null, drive_minutes: null, transfer_minutes: parks[i].transfer_minutes, total_access_minutes: null, availability: "Unknown / No live occupancy feed", latitude: null, longitude: null });
        }
    }
    return {
        event: event,
        request: { event_id: event.event_id || eventId, start_location: startLocation, resolved_start: outboundBundle.start.display_name, departure_time: departureTime, return_time: returnTime },
        estimate_disclaimer: "Journey times keep the OSRM normal duration separate from the event model. Live traffic minutes are included only when a licensed measured-speed source is available.",
        outbound: Object.assign({ distance_miles: outboundBundle.routes[0].distance_miles, routes: outboundOptions }, outbound),
        return: Object.assign({ distance_miles: returnBundle.routes[0].distance_miles, routes: returnOptions }, inbound),
        crowd: crowdRiskFromEvent(event, departureTime),
        parking: parking,
        map: { start: outboundBundle.start, destination: outboundBundle.destination, outbound_routes: outboundOptions, return_routes: returnOptions, parking: parking },
        live_transport: { live_traffic: liveTraffic, live_disruptions: { available: false, status: "unavailable", items: [], source: "None configured", checked_at: liveTraffic.checked_at, note: "Local fallback does not call licensed disruption APIs." }, checked_at: liveTraffic.checked_at, limitations: "Live speed data is unavailable in the browser fallback." },
        road_conditions: { source: "TfGM", status: "configured records", note: "Verified disruption records are listed separately from modelled journey estimates." }
    };
}

function breakdownFromJourney(journey) {
    if (journey && journey.breakdown) return journey.breakdown;
    var normal = Number(journey && journey.normal_minutes) || 0;
    var extra = Number(journey && journey.extra_delay) || 0;
    var estimated = Number(journey && journey.estimated_minutes) || 0;
    return journeyBreakdown(normal, estimated, extra);
}

function displayResults(data) {
    var outbound = data.outbound || {};
    var returnJourney = data["return"] || {};
    var crowd = data.crowd || {};
    if (data.event) { cachedEvent = data.event; renderEvent(data.event); }
    displayDisruptions((data.event && (data.event.verified_disruptions || data.event.disruptions)) || []);
    displayLiveTransport(data.live_transport || {}, outbound);
    document.getElementById("outboundDistance").textContent = outbound.distance_miles != null ? outbound.distance_miles + " miles" : "-";
    document.getElementById("outboundTime").textContent = outbound.estimated_minutes != null ? outbound.estimated_minutes + " min" : "-";
    document.getElementById("arrivalTime").textContent = formatArrivalValue(outbound);
    document.getElementById("outboundRisk").textContent = outbound.risk || "-";
    displayJourneySummary(data);
    displayRouteComparison(outbound.routes || []);
    renderJourneyMap(data);
    var resolvedOrigin = (data.request && (data.request.resolved_start || data.request.start_location)) || "-";
    var breakdown = breakdownFromJourney(outbound);
    document.getElementById("outboundDetails").innerHTML =
        row("Resolved origin", escapeHtml(resolvedOrigin)) +
        row("Normal route", formatValue(breakdown.normal_minutes, "min")) +
        row("Live traffic", (breakdown.live_traffic_available && breakdown.live_traffic_minutes != null) ? signedMinutes(breakdown.live_traffic_minutes) : "Unavailable") +
        row("Event impact", signedMinutes(breakdown.event_impact_minutes)) +
        row("Additional event delay", signedMinutes(breakdown.extra_delay_minutes)) +
        row("Estimated journey", formatValue(breakdown.estimated_minutes, "min")) +
        row("Traffic factor", outbound.factor != null ? outbound.factor + "x" : "-") +
        row("Condition", escapeHtml(outbound.label || "-")) +
        note(data.estimate_disclaimer || "OSRM normal time is not replaced by live traffic.");
    document.getElementById("crowdDetails").innerHTML =
        row("Risk level", escapeHtml(crowd.level || "-")) +
        row("Risk score", crowd.score != null ? crowd.score + "/6" : "-") +
        row("Factors", escapeHtml((crowd.reasons || []).join(", ") || "-"));
    var returnBreakdown = breakdownFromJourney(returnJourney);
    document.getElementById("returnDetails").innerHTML =
        row("Normal route", formatValue(returnBreakdown.normal_minutes, "min")) +
        row("Live traffic", (returnBreakdown.live_traffic_available && returnBreakdown.live_traffic_minutes != null) ? signedMinutes(returnBreakdown.live_traffic_minutes) : "Unavailable") +
        row("Event impact", signedMinutes(returnBreakdown.event_impact_minutes)) +
        row("Additional event delay", signedMinutes(returnBreakdown.extra_delay_minutes)) +
        row("Estimated journey", formatValue(returnBreakdown.estimated_minutes, "min")) +
        row("Estimated arrival", escapeHtml(formatArrivalValue(returnJourney))) +
        row("Day rollover", returnJourney.day_rollover ? "Yes (" + escapeHtml(formatArrivalValue(returnJourney)) + ")" : "No") +
        row("Return risk", escapeHtml(returnJourney.risk || "-")) +
        row("Condition", escapeHtml(returnJourney.label || "-")) +
        note("Return times use the same layered method. Live minutes are only added when a measured source is available.");
    displayParking(data.parking);
    displayTransport(data.road_conditions);
}

function displayLiveTransport(liveTransport, outbound) {
    var container = document.getElementById("liveTransportDetails");
    if (!container) return;
    liveTransport = liveTransport || {};
    var live = liveTransport.live_traffic || { available: false, status: "unavailable", additional_minutes: null, source: "None configured", checked_at: liveTransport.checked_at, note: liveTransport.limitations || "Live speed data is unavailable." };
    var disruptions = liveTransport.live_disruptions || {};
    var items = disruptions.items || [];
    var statusLabel = live.available ? "Live" : (live.status === "stale" ? "Stale" : "Unavailable");
    var liveValue = live.available && live.additional_minutes != null ? signedMinutes(live.additional_minutes) : "Unavailable";
    var breakdown = breakdownFromJourney(outbound || {});
    var age = live.age_minutes;
    if (age == null && live.checked_at) {
        var checked = Date.parse(live.checked_at);
        if (!isNaN(checked)) age = Math.max(0, Math.round((Date.now() - checked) / 60000));
    }
    var freshness = age == null ? "Updated time unknown" : (age <= 0 ? "Updated just now" : (age === 1 ? "Updated 1 minute ago" : "Updated " + age + " minutes ago"));
    var html = '<div class="live-status-row"><span class="live-pill">' + escapeHtml(statusLabel) + "</span><span>" + escapeHtml(freshness) + "</span></div>";
    html += row("Source", escapeHtml(live.source || "None configured"));
    html += row("Live traffic", liveValue);
    html += row("Normal route", formatValue(breakdown.normal_minutes, "min"));
    html += row("Event impact", signedMinutes(breakdown.event_impact_minutes));
    html += row("Estimated journey", formatValue(breakdown.estimated_minutes, "min"));
    html += note(live.note || "Live traffic is shown only when a measured source is available.");
    if (items.length) {
        html += "<h4>Live disruptions</h4>";
        html += items.map(function (item) {
            return '<div class="parking-option"><h4>' + escapeHtml(item.title) + "</h4>" +
                row("Type", escapeHtml(item.type || "-")) +
                row("Affected road / location", escapeHtml(item.affected_road || item.location || "-")) +
                row("Period", escapeHtml((item.start || "-") + " -> " + (item.end || "-"))) +
                row("Severity / status", escapeHtml((item.severity || "-") + " / " + (item.status || "-"))) +
                row("Source", escapeHtml(item.source || "-")) +
                row("Retrieved", escapeHtml(item.checked_at || liveTransport.checked_at || "-")) + "</div>";
        }).join("");
    } else {
        html += note(disruptions.note || "No structured live disruption records were returned. Configured event disruptions remain listed above and are not labelled live.");
    }
    container.innerHTML = html;
}

function displayJourneySummary(data) {
    var container = document.getElementById("journeySummary");
    if (!container) return;
    var outbound = data.outbound || {};
    var inbound = data["return"] || {};
    container.innerHTML =
        '<div class="summary-split">' +
        '<div><h4>Outbound</h4>' +
        row("Distance", outbound.distance_miles != null ? outbound.distance_miles + " miles" : "-") +
        row("Estimated time", formatValue(outbound.estimated_minutes, "min")) +
        row("Arrival", escapeHtml(formatArrivalValue(outbound))) +
        row("Risk", escapeHtml(outbound.risk || "-")) +
        row("Event condition", escapeHtml(outbound.label || "-")) +
        "</div>" +
        '<div><h4>Return</h4>' +
        row("Estimated time", formatValue(inbound.estimated_minutes, "min")) +
        row("Arrival", escapeHtml(formatArrivalValue(inbound))) +
        row("Risk", escapeHtml(inbound.risk || "-")) +
        row("Day rollover", inbound.day_rollover ? "Yes" : "No") +
        "</div></div>";
}

function displayRouteComparison(routes) {
    var container = document.getElementById("routeComparison");
    if (!container) return;
    if (!routes || !routes.length) {
        container.innerHTML = "<p>No alternative routes were returned by the routing service.</p>";
        return;
    }
    var rows = routes.map(function (route) {
        return "<tr><td>" + escapeHtml(route.label || "Route") + "</td><td>" +
            (route.distance_miles != null ? route.distance_miles + " miles" : "-") + "</td><td>" +
            formatValue(route.normal_minutes, "min") + "</td><td>" +
            formatValue(route.estimated_minutes, "min") + "</td></tr>";
    }).join("");
    var noteText = routes.length < 2
        ? "The routing service returned one route. No alternatives were fabricated."
        : "Figures are event-adjusted estimates, not live traffic speeds. Routes are listed without subjective ranking.";
    container.innerHTML = '<table class="route-table"><thead><tr><th>Route</th><th>Distance</th><th>Normal duration</th><th>Estimated duration</th></tr></thead><tbody>' + rows + "</tbody></table>" + note(noteText);
}

function renderJourneyMap(data) {
    var element = document.getElementById("journeyMap");
    if (!element || typeof L === "undefined") return;
    var mapData = data.map || {};
    if (!journeyMap) {
        journeyMap = L.map("journeyMap");
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 18,
            attribution: "&copy; OpenStreetMap contributors"
        }).addTo(journeyMap);
    }
    journeyMapLayers.forEach(function (layer) { journeyMap.removeLayer(layer); });
    journeyMapLayers = [];
    var bounds = [];
    function addMarker(lat, lon, title) {
        if (lat == null || lon == null) return;
        var marker = L.marker([lat, lon]).addTo(journeyMap).bindPopup(title);
        journeyMapLayers.push(marker);
        bounds.push([lat, lon]);
    }
    if (mapData.start) addMarker(mapData.start.latitude, mapData.start.longitude, "Start: " + (mapData.start.display_name || "Origin"));
    if (mapData.destination) addMarker(mapData.destination.latitude, mapData.destination.longitude, "Event: " + (mapData.destination.display_name || "Destination"));
    (mapData.parking || data.parking || []).forEach(function (site) {
        addMarker(site.latitude, site.longitude, site.name || "Park & Ride");
    });
    (mapData.outbound_routes || data.outbound && data.outbound.routes || []).forEach(function (route, index) {
        if (!route.geometry || !route.geometry.length) return;
        var line = L.polyline(route.geometry, {
            color: index === 0 ? "#2563eb" : "#64748b",
            weight: index === 0 ? 5 : 3,
            opacity: index === 0 ? 0.9 : 0.65,
            dashArray: index === 0 ? null : "8 6"
        }).addTo(journeyMap).bindPopup(route.label || "Route");
        journeyMapLayers.push(line);
        route.geometry.forEach(function (point) { bounds.push(point); });
    });
    if (bounds.length) {
        journeyMap.fitBounds(bounds, { padding: [24, 24] });
    } else {
        journeyMap.setView([53.4631, -2.2913], 10);
    }
    setTimeout(function () { journeyMap.invalidateSize(); }, 200);
}

function signedMinutes(value) {
    if (value === null || value === undefined) return "Unavailable";
    var number = Number(value);
    if (!isFinite(number)) return "Unavailable";
    var prefix = number > 0 ? "+" : "";
    return prefix + number + " min";
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
            note("Configured / verified disruption information. This is not a live traffic measurement.") + '</div>';
    }).join("");
}

function escapeHtml(value) {
    var el = document.createElement("div");
    el.textContent = String(value == null ? "" : value);
    return el.innerHTML;
}
