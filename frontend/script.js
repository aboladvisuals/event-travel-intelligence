document.addEventListener("DOMContentLoaded", function () { loadEvents(); });

var API_URL = "https://event-travel-intelligence.onrender.com";
var DEFAULT_EVENT_ID = "nsppd-uk-old-trafford-2026";
var EVENT_ALIASES = { "nspdp-uk-old-trafford-2026": DEFAULT_EVENT_ID };
var analyzeButton = document.getElementById("analyzeButton");
var statusElement = document.getElementById("status");
var resultsSection = document.getElementById("results");
var eventSearch = document.getElementById("eventSearch");
var eventResults = document.getElementById("eventResults");
var eventSearchStatus = document.getElementById("eventSearchStatus");
var selectedEventBanner = document.getElementById("selectedEventBanner");
var cachedEvent = null;
var cachedEvents = [];
var selectedEventId = null;
var searchTimer = null;

if (analyzeButton) analyzeButton.addEventListener("click", analyzeJourney);
if (eventSearch) {
    eventSearch.addEventListener("input", function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () { renderEventResults(eventSearch.value); }, 150);
    });
    eventSearch.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            renderEventResults(eventSearch.value);
        }
    });
}

async function fetchJson(url, options, timeoutMs) {
    options = options || {};
    timeoutMs = timeoutMs || 20000;
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs);
    try { return await fetch(url, Object.assign({}, options, { signal: controller.signal })); }
    finally { clearTimeout(timer); }
}

function resolveEventId(eventId) { return EVENT_ALIASES[eventId] || eventId || DEFAULT_EVENT_ID; }

function eventLabel(event) {
    var name = event.name || event.event_id;
    return event.fictional ? name + " (fictional / development only)" : name;
}

function formatDate(value) {
    if (!value) return "";
    var date = new Date(value + "T00:00:00");
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function matchesQuery(event, query) {
    var needle = String(query || "").trim().toLowerCase();
    if (!needle) return true;
    var haystack = [event.name, event.venue, event.city, event.country, event.destination].join(" ").toLowerCase();
    return haystack.indexOf(needle) !== -1;
}

function filterEvents(query) {
    return cachedEvents.filter(function (event) { return matchesQuery(event, query); });
}

function renderEventResults(query) {
    if (!eventResults) return;
    var matches = filterEvents(query);
    eventResults.innerHTML = "";
    if (!matches.length) {
        if (eventSearchStatus) eventSearchStatus.textContent = "No matching events found.";
        return;
    }
    if (eventSearchStatus) eventSearchStatus.textContent = matches.length + " event" + (matches.length === 1 ? "" : "s") + " found.";
    matches.forEach(function (event) {
        var card = document.createElement("article");
        card.className = "event-card" + (event.event_id === selectedEventId ? " selected" : "");
        card.setAttribute("role", "listitem");
        var heading = document.createElement("h3");
        heading.textContent = event.name;
        var place = document.createElement("p");
        place.textContent = [event.venue, event.city].filter(Boolean).join(" · ");
        var dateLine = document.createElement("p");
        dateLine.className = "event-date";
        dateLine.textContent = event.fictional ? "Development test event" : formatDate(event.date);
        card.appendChild(heading);
        card.appendChild(place);
        card.appendChild(dateLine);
        if (event.fictional) {
            var tag = document.createElement("p");
            tag.className = "fictional-tag";
            tag.textContent = "Fictional / development only";
            card.appendChild(tag);
        }
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = event.event_id === selectedEventId ? "Selected" : "Select Event";
        button.setAttribute("aria-pressed", event.event_id === selectedEventId ? "true" : "false");
        button.addEventListener("click", function () { selectEvent(event.event_id); });
        card.appendChild(button);
        eventResults.appendChild(card);
    });
}

async function loadEvents() {
    try {
        var listResponse = await fetchJson(API_URL + "/events", {}, 12000);
        if (!listResponse.ok) throw new Error("API events request failed");
        cachedEvents = await listResponse.json();
        renderEventResults("");
        await selectEvent(DEFAULT_EVENT_ID);
        return;
    } catch (apiError) {
        try {
            var localList = await fetchJson("events.json", {}, 8000);
            if (!localList.ok) throw new Error("Local events file missing");
            cachedEvents = await localList.json();
            renderEventResults("");
            await selectEvent(DEFAULT_EVENT_ID);
            if (statusElement) statusElement.textContent = "Events loaded from local configuration. Analyse Journey uses the public API when CORS is available.";
        } catch (localError) {
            try {
                var local = await fetchJson("event.json", {}, 8000);
                if (!local.ok) throw new Error("Local event file missing");
                cachedEvent = await local.json();
                cachedEvents = [cachedEvent];
                renderEventResults("");
                await selectEvent(cachedEvent.event_id || DEFAULT_EVENT_ID);
            } catch (fallbackError) {
                document.getElementById("eventName").textContent = "Event Travel Intelligence";
                if (eventSearchStatus) eventSearchStatus.textContent = "Could not load event configuration.";
                if (statusElement) statusElement.textContent = "Could not load event configuration.";
            }
        }
    }
}

async function selectEvent(eventId) {
    var resolvedId = resolveEventId(eventId);
    selectedEventId = resolvedId;
    try {
        var response = await fetchJson(API_URL + "/events/" + encodeURIComponent(resolvedId), {}, 12000);
        if (!response.ok) throw new Error("API event request failed");
        cachedEvent = await response.json();
    } catch (apiError) {
        cachedEvent = findLocalEvent(resolvedId);
        if (!cachedEvent) {
            var local = await fetchJson("event.json", {}, 8000);
            if (!local.ok) throw new Error("Could not load selected event");
            cachedEvent = await local.json();
        }
    }
    selectedEventId = cachedEvent.event_id || resolvedId;
    renderEvent(cachedEvent);
    renderEventResults(eventSearch ? eventSearch.value : "");
    displayDisruptions(cachedEvent.verified_disruptions || cachedEvent.disruptions || []);
}

function findLocalEvent(eventId) {
    var resolvedId = resolveEventId(eventId);
    for (var i = 0; i < cachedEvents.length; i++) {
        if (cachedEvents[i].event_id === resolvedId) return cachedEvents[i];
    }
    return null;
}

function renderEvent(event) {
    var eventName = document.getElementById("eventName");
    var eventMeta = document.getElementById("eventMeta");
    var destinationInput = document.getElementById("destination");
    if (eventName) eventName.textContent = eventLabel(event);
    if (destinationInput) {
        destinationInput.value = event.destination || "";
        destinationInput.placeholder = event.destination || "Event destination";
    }
    var traffic = event.traffic_management || {};
    var trafficStart = event.traffic_management_start || traffic.start;
    var trafficEnd = event.traffic_management_end || traffic.end;
    var metaParts = [
        event.venue,
        event.city,
        event.fictional ? "Development test event" : formatDate(event.date),
        event.capacity ? ("Capacity " + Number(event.capacity).toLocaleString("en-GB")) : null,
        trafficStart && trafficEnd ? ("Traffic management " + trafficStart + "-" + trafficEnd) : null
    ].filter(Boolean);
    if (eventMeta) eventMeta.textContent = metaParts.join(" | ");
    if (selectedEventBanner) {
        selectedEventBanner.innerHTML =
            "<strong>" + escapeHtml(eventLabel(event)) + "</strong>" +
            escapeHtml([event.venue, event.city].filter(Boolean).join(" · ")) +
            (event.fictional ? "<div class=\"fictional-tag\">Fictional / development only</div>" : "<div>" + escapeHtml(formatDate(event.date)) + "</div>");
    }
}

async function analyzeJourney() {
    var startLocation = document.getElementById("startLocation").value.trim();
    var destination = document.getElementById("destination").value.trim();
    var departureTime = document.getElementById("departureTime").value;
    var returnTime = document.getElementById("returnTime").value;
    var eventId = selectedEventId || (cachedEvent && cachedEvent.event_id);
    if (!eventId) {
        statusElement.textContent = "Select an event before analysing a journey.";
        return;
    }
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
                event_id: eventId,
                start_location: startLocation,
                destination: destination,
                departure_time: departureTime,
                return_time: returnTime
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
            displayResults(await analyzeLocally(startLocation, destination, departureTime, returnTime, eventId));
            statusElement.textContent = "Analysis complete via routing services. Times shown are event-adjusted estimates, not live traffic speeds.";
            resultsSection.classList.remove("hidden");
        } catch (localError) {
            statusElement.textContent = "Error: " + (localError.message || error.message);
        }
    } finally {
        analyzeButton.disabled = false;
    }
}
