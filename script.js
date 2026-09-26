document.addEventListener("DOMContentLoaded", function () { loadEvents(); });

var API_URL = "https://event-travel-intelligence.onrender.com";
var DEFAULT_EVENT_ID = "nsppd-uk-old-trafford-2026";
var EVENT_ALIASES = { "nspdp-uk-old-trafford-2026": DEFAULT_EVENT_ID };
var analyzeButton = document.getElementById("analyzeButton");
var statusElement = document.getElementById("status");
var resultsSection = document.getElementById("results");
var eventSelect = document.getElementById("eventSelect");
var cachedEvent = null;
var cachedEvents = [];

if (analyzeButton) analyzeButton.addEventListener("click", analyzeJourney);
if (eventSelect) eventSelect.addEventListener("change", function () { selectEvent(eventSelect.value); });

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
function populateEventSelect(events, selectedId) {
    if (!eventSelect) return;
    eventSelect.innerHTML = "";
    events.forEach(function (event) {
        var option = document.createElement("option");
        option.value = event.event_id;
        option.textContent = eventLabel(event);
        eventSelect.appendChild(option);
    });
    if (selectedId) eventSelect.value = selectedId;
}

async function loadEvents() {
    var selectedId = DEFAULT_EVENT_ID;
    try {
        var listResponse = await fetchJson(API_URL + "/events", {}, 12000);
        if (!listResponse.ok) throw new Error("API events request failed");
        cachedEvents = await listResponse.json();
        populateEventSelect(cachedEvents, selectedId);
        await selectEvent(selectedId);
        return;
    } catch (apiError) {
        try {
            var localList = await fetchJson("events.json", {}, 8000);
            if (!localList.ok) throw new Error("Local events file missing");
            cachedEvents = await localList.json();
            populateEventSelect(cachedEvents, selectedId);
            await selectEvent(selectedId);
            if (statusElement) statusElement.textContent = "Events loaded from local configuration. Analyze Journey uses the public API when CORS is available.";
        } catch (localError) {
            try {
                var local = await fetchJson("event.json", {}, 8000);
                if (!local.ok) throw new Error("Local event file missing");
                cachedEvent = await local.json();
                cachedEvents = [cachedEvent];
                populateEventSelect(cachedEvents, cachedEvent.event_id || DEFAULT_EVENT_ID);
                renderEvent(cachedEvent);
                displayDisruptions(cachedEvent.verified_disruptions || cachedEvent.disruptions || []);
            } catch (fallbackError) {
                document.getElementById("eventName").textContent = "Event Travel Intelligence";
                document.getElementById("destination").value = "Old Trafford, Manchester, UK";
                if (statusElement) statusElement.textContent = "Could not load event configuration.";
            }
        }
    }
}

async function selectEvent(eventId) {
    var resolvedId = resolveEventId(eventId);
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
    renderEvent(cachedEvent);
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
    if (eventMeta) {
        var traffic = event.traffic_management || {};
        var trafficStart = event.traffic_management_start || traffic.start;
        var trafficEnd = event.traffic_management_end || traffic.end;
        eventMeta.textContent = [
            event.venue, event.city, formatDate(event.date),
            event.capacity ? ("Capacity " + Number(event.capacity).toLocaleString("en-GB")) : null,
            trafficStart && trafficEnd ? ("Traffic management " + trafficStart + "-" + trafficEnd) : null
        ].filter(Boolean).join(" | ");
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
    var eventId = (eventSelect && eventSelect.value) || (cachedEvent && cachedEvent.event_id) || DEFAULT_EVENT_ID;
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
