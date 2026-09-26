# Event Travel Intelligence

Public app for planning travel to a major event using routing data, configured event conditions, verified transport disruptions and Park & Ride access times.

Live frontend: https://aboladvisuals.github.io/event-travel-intelligence/

Live API: https://event-travel-intelligence.onrender.com

Current production event: **NSPPD UK Prayer Conference**, Old Trafford, Manchester, 26 September 2026.

## Dynamic Event Engine

Events are configuration data. Travel intelligence is a separate engine that consumes an event object.

```
EVENT DATA
    ↓
EVENT STORE (JSON files)
    ↓
TRAVEL INTELLIGENCE ENGINE
    ↓
JOURNEY ANALYSIS
    ↓
FRONTEND
```

- Event records live in `data/events/*.json`.
- The reusable schema is `backend/event_model.py`.
- The store is `backend/event_store.py`.
- `backend/travel_engine.py` reads traffic-management windows, start/end times, capacity and destination from the selected event. It does not hardcode NSPPD.
- Adding another event means adding event data, not rewriting the travel engine.
- The current NSPPD event (`nsppd-uk-old-trafford-2026`) is the production example.
- `test-event-manchester` is fictional and for development only. It exists to prove the engine reads event configuration dynamically. It must not be presented as a real event.

The frontend loads available events from `GET /events` and can search them. If the public API is blocked, it falls back to same-origin `events.json` / `event.json` and can still calculate an event-adjusted route with Nominatim + OSRM.

## Event Discovery

Users do not need to know event IDs. They can search or browse configured events, then select one before analysing a journey.

- Search covers event name, venue, city and country.
- `GET /events/search?q=` filters the JSON event store in memory.
- `GET /events?from=&to=` optionally filters by event date.
- Selecting an event loads `GET /events/{event_id}` and that event controls destination, traffic windows, disruptions, parking and `/analyze`.
- The fictional Manchester test event stays labelled development-only.

## Journey Intelligence

After an event is selected, journey analysis shows more than a single time.

- OSRM is asked for alternative driving routes and full geometry when the public router returns them. Alternatives are never invented.
- Each route lists distance, normal duration and event-adjusted duration.
- The time breakdown is `normal + event adjustment + additional event delay = estimated`.
- A Leaflet map (OpenStreetMap tiles, no API key) plots origin, destination, outbound route geometry and Park & Ride sites when coordinates are available.
- The journey summary covers outbound distance, estimated time, arrival, risk and event condition, plus return estimated time, arrival, risk and day rollover.
- Results remain estimates, not live traffic speeds.

## Problem being solved

Large events create congestion, road restrictions and uncertain parking. People leaving from different towns need a single place to:

- search or browse configured events
- enter any reasonable starting location
- see the event destination and traffic-management window
- get an estimated outbound and return journey
- see crowd / event-period risk
- see verified disruption records
- compare Park & Ride options associated with that event

The app does **not** pretend to be a live traffic-speed or live parking-occupancy product.

## Architecture

```
Browser (GitHub Pages)
    GET  /events                 (Render API, with events.json fallback)
    GET  /events/search?q=       (Render API, with local filter fallback)
    GET  /events/{event_id}      (Render API, with local event fallback)
    GET  /event                  (legacy default event)
    POST /analyze                (Render API, with Nominatim + OSRM fallback)
        -> FastAPI on Render
            -> Event store
            -> Nominatim geocoding (UK-biased)
            -> OSRM driving routes (alternatives + GeoJSON when available)
            -> Event-configured timing, disruptions and parking
            -> Journey breakdown, route comparison and map payload
```

- **Frontend**: static HTML, CSS and JavaScript on GitHub Pages.
- **Backend**: FastAPI (`backend/main.py`) deployed on Render.
- **Nominatim**: geocodes any user-supplied origin (and parking sites) to coordinates. Ambiguous UK names prefer `countrycodes=gb`.
- **OSRM**: public driving router used for a *normal* route distance and duration. Journey analysis requests `alternatives=true` and GeoJSON geometry when available; alternatives are never invented.
- **Leaflet map**: OpenStreetMap tiles on the results page show origin, destination, outbound route geometry and Park & Ride markers. No mapping API key is required.
- **Event intelligence**: selected event venue, date, capacity and traffic-management window.
- **Disruption intelligence**: verified records stored on the event, attributed to TfGM for the production event.
- **Park & Ride intelligence**: options configured on the selected event. Drive time from the origin plus a configured transfer time.

The original Pages failure (`Loading event...`) was caused by the browser blocking the public API because CORS headers were missing. The backend includes FastAPI CORS middleware. The frontend still calls the public API first. If the browser cannot read that response, it falls back to same-origin event files and can calculate an event-adjusted route so the public site keeps working.

## Important limitations

- **Parking availability is currently not live occupancy data.** The UI labels this as `Unknown / No live occupancy feed`.
- **Journey times are event-adjusted estimates and are not measured live traffic speeds.** The estimate is:

  `estimated_minutes = round(normal_OSRM_minutes * event_factor + extra_event_delay)`

- Verified disruption records are separate from modelled travel estimates.
- Nominatim is a public geocoder and may rate-limit requests. The backend caches coordinates and retries 429 responses.
- The destination is the selected event venue, not an arbitrary second user destination.
- The test event is fictional and must not be treated as production information.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service name, status, default event and version `1.3.0` |
| GET | `/health` | Health check |
| GET | `/events` | Available events (`from` / `to` date filters optional) |
| GET | `/events/search` | Search events by name, venue, city or country |
| GET | `/events/{event_id}` | Full configuration for one event |
| GET | `/event` | Legacy default/current event (NSPPD) |
| POST | `/analyze` | Geocode origin, route to selected event, event-adjusted times, crowd risk, parking, transport status |

### Example analyze payload

```json
{
  "event_id": "nsppd-uk-old-trafford-2026",
  "start_location": "Southampton",
  "departure_time": "08:00",
  "return_time": "20:30"
}
```

If `event_id` is omitted, the backend uses the production NSPPD event. `destination` may be sent by the frontend, but routing uses the selected event destination.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
python tests/test_event_engine.py
python tests/test_event_discovery.py
python tests/test_journey_intelligence.py
```

Open the repository-root GitHub Pages files (`index.html`, `style.css`, `script.js`) or `frontend/index.html` with a local static server.

The frontend calls the public Render API by default:

`https://event-travel-intelligence.onrender.com`

## Deployment

- Backend: Render web service from this repository, command typically `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- After pushing backend changes, trigger a Render deploy if auto-deploy is off. The live API should report version `1.3.0` and send `Access-Control-Allow-Origin` for `https://aboladvisuals.github.io`.
- Frontend: GitHub Pages from the repository root so `/event-travel-intelligence/` serves `index.html`.
- CORS is configured in `backend/main.py` for `https://aboladvisuals.github.io` and other `*.github.io` origins.

Do not commit `.env` files, secrets or API keys.

## Future improvements

Deferred to later phases:

- A reliable live parking-occupancy source, clearly labelled as live only if the feed is real
- Official TfGM / National Highways structured disruption APIs
- A measured traffic source if one is licensed
- User accounts
- Persist geocode cache beyond a single process
