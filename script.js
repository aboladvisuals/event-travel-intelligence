document.addEventListener("DOMContentLoaded", () => {
    loadEvent();
});

const API_URL = "https://event-travel-intelligence.onrender.com";

const analyzeButton = document.getElementById("analyzeButton");
const statusElement = document.getElementById("status");
const resultsSection = document.getElementById("results");

if (analyzeButton) {
    analyzeButton.addEventListener("click", analyzeJourney);
}

async function fetchJson(url, options = {}, timeoutMs = 25000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
        });
        return response;
    } finally {
        clearTimeout(timer);
    }
}

async function loadEvent() {
    const eventName = document.getElementById("eventName");
    const eventMeta = document.getElementById("eventMeta");
    const destinationInput = document.getElementById("destination");

    let lastError = null;

    for (let attempt = 1; attempt <= 3; attempt += 1) {
        try {
            const response = await fetchJson(`${API_URL}/event`);

            if (!response.ok) {
                throw new Error(`Could not load event (${response.status}).`);
            }

            const event = await response.json();
            renderEvent(event);
            displayDisruptions(event.verified_disruptions || []);
            return;
        } catch (error) {
            lastError = error;
            if (eventName) {
                eventName.textContent = "Loading event…";
            }
            if (statusElement) {
                statusElement.textContent =
                    attempt < 3
                        ? "Connecting to event API…"
                        : "Could not load event configuration.";
            }
            await new Promise((resolve) => setTimeout(resolve, 1200 * attempt));
        }
    }

    if (eventName) {
        eventName.textContent = "Event Travel Intelligence";
    }
    if (destinationInput && !destinationInput.value) {
        destinationInput.placeholder = "Old Trafford, Manchester, UK";
    }
    if (eventMeta) {
        eventMeta.textContent =
            "Event details could not be loaded from the public API. You can still enter a starting location after the API is reachable.";
    }
    if (statusElement) {
        statusElement.textContent =
            `Could not load event configuration. ${lastError ? lastError.message : ""}`.trim();
    }
}

function renderEvent(event) {
    const eventName = document.getElementById("eventName");
    const eventMeta = document.getElementById("eventMeta");
    const destinationInput = document.getElementById("destination");

    if (eventName) {
        eventName.textContent = event.name || "Event Travel Intelligence";
    }

    if (destinationInput) {
        destinationInput.value = event.destination || "";
        destinationInput.placeholder = event.destination || "Event destination";
    }

    if (eventMeta) {
        const parts = [
            event.venue,
            event.city,
            formatDate(event.date),
            event.capacity ? `Capacity ${Number(event.capacity).toLocaleString("en-GB")}` : null,
            event.traffic_management
                ? `Traffic management ${event.traffic_management.start}–${event.traffic_management.end}`
                : null,
        ].filter(Boolean);
        eventMeta.textContent = parts.join(" \u00b7 ");
    }

    if (statusElement) {
        statusElement.textContent = "";
    }
}

function formatDate(value) {
    if (!value) {
        return "";
    }
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleDateString("en-GB", {
        day: "numeric",
        month: "long",
        year: "numeric",
    });
}

async function analyzeJourney() {
    const startLocation = document.getElementById("startLocation").value.trim();
    const destination = document.getElementById("destination").value.trim();
    const departureTime = document.getElementById("departureTime").value;
    const returnTime = document.getElementById("returnTime").value;

    if (!startLocation || !destination || !departureTime || !returnTime) {
        statusElement.textContent = "Please complete all fields.";
        return;
    }

    analyzeButton.disabled = true;
    statusElement.textContent =
        "Analyzing route, event conditions and parking. This can take a few seconds…";
    resultsSection.classList.add("hidden");

    try {
        const response = await fetchJson(`${API_URL}/analyze`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                start_location: startLocation,
                destination: destination,
                departure_time: departureTime,
                return_time: returnTime,
                event_capacity: 50000,
            }),
        }, 90000);

        let data = null;
        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error("The API did not return valid JSON.");
        }

        if (!response.ok) {
            const detail = Array.isArray(data && data.detail)
                ? data.detail.map((item) => item.msg || item).join(" ")
                : (data && data.detail) || "Analysis failed.";
            throw new Error(detail);
        }

        displayResults(data);
        statusElement.textContent = "Analysis complete. Times shown are event-adjusted estimates, not live traffic speeds.";
        resultsSection.classList.remove("hidden");
    } catch (error) {
        const message = error.name === "AbortError"
            ? "The request timed out. Please try again."
            : error.message;
        statusElement.textContent = `Error: ${message}`;
    } finally {
        analyzeButton.disabled = false;
    }
}

function displayResults(data) {
    const outbound = data.outbound || {};
    const returnJourney = data.return || {};
    const crowd = data.crowd || {};

    displayDisruptions((data.event && data.event.verified_disruptions) || []);

    document.getElementById("outboundDistance").textContent =
        outbound.distance_miles != null ? `${outbound.distance_miles} miles` : "\u2014";
    document.getElementById("outboundTime").textContent =
        outbound.estimated_minutes != null ? `${outbound.estimated_minutes} min` : "\u2014";
    document.getElementById("arrivalTime").textContent = outbound.arrival_time || "\u2014";
    document.getElementById("outboundRisk").textContent = outbound.risk || "\u2014";

    const resolvedOrigin = (data.request && (data.request.resolved_start || data.request.start_location)) || "\u2014";

    document.getElementById("outboundDetails").innerHTML =
        row("Resolved origin", escapeHtml(resolvedOrigin)) +
        row("Normal driving time (OSRM)", formatValue(outbound.normal_minutes, "min")) +
        row("Estimated event-adjusted time", formatValue(outbound.estimated_minutes, "min")) +
        row("Traffic factor", outbound.factor != null ? `${outbound.factor}\u00d7` : "\u2014") +
        row("Additional event-related delay", formatValue(outbound.extra_delay, "min")) +
        row("Condition", escapeHtml(outbound.label || "\u2014")) +
        `<p class="note">${escapeHtml(data.estimate_disclaimer || "Journey times are event-adjusted estimates and are not measured live traffic speeds.")}</p>`;

    document.getElementById("crowdDetails").innerHTML =
        row("Risk level", escapeHtml(crowd.level || "\u2014")) +
        row("Risk score", crowd.score != null ? `${crowd.score}/6` : "\u2014") +
        row("Factors", escapeHtml((crowd.reasons || []).join(", ") || "\u2014"));

    document.getElementById("returnDetails").innerHTML =
        row("Normal driving time (OSRM)", formatValue(returnJourney.normal_minutes, "min")) +
        row("Estimated return time", formatValue(returnJourney.estimated_minutes, "min")) +
        row("Estimated arrival", escapeHtml(returnJourney.arrival_time || "\u2014")) +
        row("Return risk", escapeHtml(returnJourney.risk || "\u2014")) +
        row("Condition", escapeHtml(returnJourney.label || "\u2014")) +
        `<p class="note">Return times are modelled from the same event-adjustment method. They are not live measured speeds.</p>`;

    displayParking(data.parking);
    displayTransport(data.road_conditions);
}

function row(label, value) {
    return `<div class="detail-row"><span class="detail-label">${label}</span><strong>${value}</strong></div>`;
}

function displayParking(parkingOptions) {
    const container = document.getElementById("parkingDetails");

    if (!parkingOptions || parkingOptions.length === 0) {
        container.innerHTML = "<p>No parking options available.</p>";
        return;
    }

    const cards = parkingOptions.map((option) => {
        const distance = option.distance_miles != null ? `${option.distance_miles} miles` : "Unavailable";
        return `<div class="parking-option">` +
            `<h4>${escapeHtml(option.name)}</h4>` +
            row("Location", escapeHtml(option.location || "\u2014")) +
            row("Driving distance", distance) +
            row("Driving time", formatValue(option.drive_minutes, "min")) +
            row("Transfer time", formatValue(option.transfer_minutes, "min")) +
            row("Estimated total journey time", formatValue(option.total_access_minutes, "min")) +
            row("Availability", escapeHtml(option.availability || "Unknown / No live occupancy feed")) +
            `</div>`;
    }).join("");

    container.innerHTML = `<p class="note">Parking availability is currently not live occupancy data. Figures below are drive + transfer estimates only.</p>${cards}`;
}

function displayTransport(roadConditions) {
    const container = document.getElementById("transportDetails");
    if (!container) {
        return;
    }

    if (!roadConditions) {
        container.innerHTML = "<p>No additional transport information is available.</p>";
        return;
    }

    container.innerHTML =
        row("Source", escapeHtml(roadConditions.source || "TfGM")) +
        row("Feed status", escapeHtml(roadConditions.status || "unknown")) +
        `<p class="note">${escapeHtml(roadConditions.note || "Verified disruption records are listed separately from modelled journey estimates.")}</p>`;
}

function formatValue(value, unit) {
    if (value === null || value === undefined) {
        return "Unavailable";
    }
    return `${value} ${unit}`;
}

function displayDisruptions(disruptions) {
    const container = document.getElementById("disruptionDetails");
    if (!container) {
        return;
    }

    if (!disruptions || disruptions.length === 0) {
        container.innerHTML = "<p>No verified disruptions currently configured.</p>";
        return;
    }

    container.innerHTML = disruptions.map((item) => {
        return `<div class="parking-option">` +
            `<h4>${escapeHtml(item.title)}</h4>` +
            row("Type", escapeHtml(item.type || "\u2014")) +
            row("Period", escapeHtml(`${item.start || "\u2014"} → ${item.end || "\u2014"}`)) +
            row("Impact", escapeHtml(item.impact || "\u2014")) +
            row("Source", escapeHtml(item.source || "TfGM")) +
            `<p class="note">Verified disruption information. This is separate from modelled / event-adjusted travel estimates.</p>` +
            `</div>`;
    }).join("");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&")
        .replaceAll("<", "<")
        .replaceAll(">", ">")
        .replaceAll('"', """)
        .replaceAll("'", "&#39;");
}
