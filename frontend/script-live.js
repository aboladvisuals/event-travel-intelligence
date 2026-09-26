function liveMinutesLabel(breakdown) {
    if (breakdown && breakdown.live_traffic_available && breakdown.live_traffic_minutes != null) {
        return signedMinutes(breakdown.live_traffic_minutes);
    }
    return "Unavailable";
}

function freshnessLabel(checkedAt, ageMinutes) {
    var age = ageMinutes;
    if (age == null && checkedAt) {
        var checked = Date.parse(checkedAt);
        if (!isNaN(checked)) age = Math.max(0, Math.round((Date.now() - checked) / 60000));
    }
    if (age == null) return "Updated time unknown";
    if (age <= 0) return "Updated just now";
    if (age === 1) return "Updated 1 minute ago";
    return "Updated " + age + " minutes ago";
}

function displayLiveTransport(liveTransport, outbound) {
    var container = document.getElementById("liveTransportDetails");
    if (!container) return;
    liveTransport = liveTransport || {};
    var live = liveTransport.live_traffic || (typeof unavailableLiveTraffic === "function" ? unavailableLiveTraffic("Live speed data is unavailable.") : {
        available: false,
        status: "unavailable",
        additional_minutes: null,
        source: "None configured",
        checked_at: new Date().toISOString(),
        note: "Live speed data is unavailable."
    });
    var disruptions = liveTransport.live_disruptions || {};
    var items = disruptions.items || [];
    var statusLabel = live.available ? "Live" : (live.status === "stale" ? "Stale" : "Unavailable");
    var liveValue = live.available && live.additional_minutes != null ? signedMinutes(live.additional_minutes) : "Unavailable";
    var breakdown = typeof breakdownFromJourney === "function" ? breakdownFromJourney(outbound || {}) : {};
    var html = "";
    html += '<div class="live-status-row">';
    html += '<span class="live-pill">' + escapeHtml(statusLabel) + "</span>";
    html += "<span>" + escapeHtml(freshnessLabel(live.checked_at, live.age_minutes)) + "</span>";
    html += "</div>";
    html += row("Source", escapeHtml(live.source || "None configured"));
    html += row("Live traffic", liveValue);
    html += row("Normal route", formatValue(breakdown.normal_minutes, "min"));
    html += row("Event impact", signedMinutes(breakdown.event_impact_minutes));
    html += row("Estimated journey", formatValue(breakdown.estimated_minutes, "min"));
    html += note(live.note || liveTransport.limitations || "Live traffic is shown only when a measured source is available.");
    if (items.length) {
        html += "<h4>Live disruptions</h4>";
        html += items.map(function (item) {
            return '<div class="parking-option"><h4>' + escapeHtml(item.title) + "</h4>" +
                row("Type", escapeHtml(item.type || "-")) +
                row("Affected road / location", escapeHtml(item.affected_road || item.location || "-")) +
                row("Period", escapeHtml((item.start || "-") + " -> " + (item.end || "-"))) +
                row("Severity / status", escapeHtml((item.severity || "-") + " / " + (item.status || "-"))) +
                row("Source", escapeHtml(item.source || "-")) +
                row("Retrieved", escapeHtml(item.checked_at || liveTransport.checked_at || "-")) +
                "</div>";
        }).join("");
    } else {
        html += note(disruptions.note || "No structured live disruption records were returned. Configured event disruptions remain listed above and are not labelled live.");
    }
    container.innerHTML = html;
}

(function () {
    if (typeof displayResults !== "function") return;
    var original = displayResults;
    displayResults = function (data) {
        original(data);
        displayLiveTransport((data && data.live_transport) || {}, (data && data.outbound) || {});
    };
})();
