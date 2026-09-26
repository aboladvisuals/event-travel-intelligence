document.addEventListener("DOMContentLoaded", loadEvent);

const API_URL = "http://127.0.0.1:8001";

const analyzeButton = document.getElementById("analyzeButton");
const statusElement = document.getElementById("status");
const resultsSection = document.getElementById("results");


analyzeButton.addEventListener("click", analyzeJourney);

async function loadEvent() {

    try {

        const response = await fetch(`${API_URL}/event`);

        if (!response.ok) {
            throw new Error("Could not load event.");
        }

        const event = await response.json();

        document.getElementById("eventName").textContent =
            event.name;

        const destinationInput =
            document.getElementById("destination");

        destinationInput.value =
            event.destination;

        destinationInput.placeholder =
            event.destination;

    }

    catch (error) {

        document.getElementById("eventName").textContent =
            "Event Travel Intelligence";

        document.getElementById("status").textContent =
            "Could not load event configuration.";

    }
}
async function analyzeJourney() {

    const startLocation =
        document.getElementById("startLocation").value.trim();

    const destination =
        document.getElementById("destination").value.trim();

    const departureTime =
        document.getElementById("departureTime").value;

    const returnTime =
        document.getElementById("returnTime").value;


    if (!startLocation || !destination || !departureTime || !returnTime) {
        statusElement.textContent =
            "Please complete all fields.";

        return;
    }


    analyzeButton.disabled = true;

    statusElement.textContent =
        "Analyzing route, event conditions and parking...";

    resultsSection.classList.add("hidden");


    try {

        const response = await fetch(`${API_URL}/analyze`, {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                start_location: startLocation,
                destination: destination,
                departure_time: departureTime,
                return_time: returnTime,
                event_capacity: 50000
            })

        });


        const data = await response.json();


        if (!response.ok) {
            throw new Error(
                data.detail || "Analysis failed."
            );
        }


        displayResults(data);

        statusElement.textContent =
            "Analysis complete.";

        resultsSection.classList.remove("hidden");

    }

    catch (error) {

        statusElement.textContent =
            `Error: ${error.message}`;

    }

    finally {

        analyzeButton.disabled = false;

    }
}


function displayResults(data) {

    const outbound = data.outbound;
    const returnJourney = data.return;
    const crowd = data.crowd;
    displayDisruptions(data.event.verified_disruptions);


    document.getElementById("outboundDistance").textContent =
        `${data.outbound.distance_miles} miles`;


    document.getElementById("outboundTime").textContent =
        `${outbound.estimated_minutes} min`;


    document.getElementById("arrivalTime").textContent =
        outbound.arrival_time;


    document.getElementById("outboundRisk").textContent =
        outbound.risk;


    document.getElementById("outboundDetails").innerHTML = `

        <div class="detail-row">
            <span class="detail-label">Normal driving time</span>
            <strong>${outbound.normal_minutes} min</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Estimated event-adjusted time</span>
            <strong>${outbound.estimated_minutes} min</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Traffic factor</span>
            <strong>${outbound.factor}×</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Additional delay</span>
            <strong>${outbound.extra_delay} min</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Condition</span>
            <strong>${outbound.label}</strong>
        </div>

    `;


    document.getElementById("crowdDetails").innerHTML = `

        <div class="detail-row">
            <span class="detail-label">Risk level</span>
            <strong>${crowd.level}</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Risk score</span>
            <strong>${crowd.score}/6</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Factors</span>
            <strong>${crowd.reasons.join(", ")}</strong>
        </div>

    `;


    document.getElementById("returnDetails").innerHTML = `

        <div class="detail-row">
            <span class="detail-label">Normal driving time</span>
            <strong>${returnJourney.normal_minutes} min</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Estimated return time</span>
            <strong>${returnJourney.estimated_minutes} min</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Estimated arrival</span>
            <strong>${returnJourney.arrival_time}</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Return risk</span>
            <strong>${returnJourney.risk}</strong>
        </div>

        <div class="detail-row">
            <span class="detail-label">Condition</span>
            <strong>${returnJourney.label}</strong>
        </div>

    `;


    displayParking(data.parking);
}


function displayParking(parkingOptions) {

    const container =
        document.getElementById("parkingDetails");


    if (!parkingOptions || parkingOptions.length === 0) {

        container.innerHTML =
            "<p>No parking options available.</p>";

        return;
    }


    container.innerHTML = parkingOptions.map(option => `

        <div class="parking-option">

            <h4>${option.name}</h4>

            <div class="detail-row">
                <span class="detail-label">
                    Drive
                </span>

                <strong>
                    ${formatValue(option.drive_minutes, "min")}
                </strong>
            </div>

            <div class="detail-row">
                <span class="detail-label">
                    Transfer
                </span>

                <strong>
                    ${formatValue(option.transfer_minutes, "min")}
                </strong>
            </div>

            <div class="detail-row">
                <span class="detail-label">
                    Total access time
                </span>

                <strong>
                    ${formatValue(option.total_access_minutes, "min")}
                </strong>
            </div>

            <div class="detail-row">
                <span class="detail-label">
                    Availability
                </span>

                <strong>
                    ${option.availability}
                </strong>
            </div>

        </div>

    `).join("");
}


function formatValue(value, unit) {

    if (value === null || value === undefined) {
        return "Unavailable";
    }

    return `${value} ${unit}`;
}
function displayDisruptions(disruptions) {

    const container =
        document.getElementById("disruptionDetails");

    if (!disruptions || disruptions.length === 0) {
        container.innerHTML =
            "<p>No verified disruptions currently configured.</p>";
        return;
    }

    container.innerHTML = disruptions.map(item => `
        <div class="parking-option">

            <h4>${item.title}</h4>

            <div class="detail-row">
                <span class="detail-label">Type</span>
                <strong>${item.type}</strong>
            </div>

            <div class="detail-row">
                <span class="detail-label">Period</span>
                <strong>${item.start} → ${item.end}</strong>
            </div>

            <div class="detail-row">
                <span class="detail-label">Impact</span>
                <strong>${item.impact}</strong>
            </div>

            <div class="detail-row">
                <span class="detail-label">Source</span>
                <strong>${item.source}</strong>
            </div>

        </div>
    `).join("");
}