function occupancyAgeLabel(option) {
    if (option && option.age_minutes != null) {
        var age = Number(option.age_minutes);
        if (age === 0) return "Updated just now";
        return "Updated " + age + " min ago";
    }
    if (option && option.checked_at) return "Checked " + option.checked_at;
    return "Not updated";
}

function occupancyStateLabel(option) {
    if (option && option.occupancy_status === "stale") return "Stale";
    if (option && option.live) return "Live";
    return "Unavailable";
}

function displayParking(parkingOptions, liveParking) {
    var container = document.getElementById("parkingDetails");
    if (!container) return;
    if (!parkingOptions || !parkingOptions.length) {
        container.innerHTML = "<p>No parking options available for the selected event.</p>";
        return;
    }
    liveParking = liveParking || {};
    var feed = liveParking.feed || {};
    var intro = note("Estimated access time is drive plus transfer. Live availability is shown only when an official feed matches that facility.");
    var feedNote = liveParking.limitations || feed.note || "";
    container.innerHTML = intro + (feedNote ? note(feedNote) : "") + parkingOptions.map(function (option) {
        var availability = option.availability || "Unknown / No live occupancy feed";
        var spaces = option.spaces_remaining != null
            ? row("Spaces remaining", String(option.spaces_remaining))
            : "";
        return '<div class="parking-option">' +
            "<h4>" + escapeHtml(option.name) + "</h4>" +
            row("Location", escapeHtml(option.location || "-")) +
            row("Drive", formatValue(option.drive_minutes, "min")) +
            row("Transfer", formatValue(option.transfer_minutes, "min")) +
            row("Total access", formatValue(option.total_access_minutes, "min")) +
            row("Availability", escapeHtml(availability)) +
            spaces +
            row("Source", escapeHtml(option.source || "None configured")) +
            row("Updated", escapeHtml(occupancyAgeLabel(option))) +
            '<p class="note"><span class="live-pill">' + escapeHtml(occupancyStateLabel(option)) + "</span> " +
            escapeHtml(option.occupancy_note || "Occupancy is separate from the access-time estimate.") +
            "</p></div>";
    }).join("");
}

(function () {
    if (typeof displayResults !== "function") return;
    var original = displayResults;
    displayResults = function (data) {
        original(data);
        displayParking((data && data.parking) || [], (data && data.live_parking) || {});
    };
})();
