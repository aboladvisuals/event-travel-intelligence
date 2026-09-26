# Event Travel Intelligence

Public app for planning travel to a major event using routing data, configured event conditions, verified transport disruptions, live transport checks and Park & Ride access times.

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
LIVE TRANSPORT CHECKS
    ↓
JOURNEY ANALYSIS
    ↓
FRONTEND
```

- Event records live in `data/events/*.json`.
- The reusable schema is `backend/event_model.py`.
- The store is `backend/event_store.py`.
- `backend/travel_engine.py` reads traffic-management windows, start/end times, capacity and destination from the selected event. It does not hardcode NSPPD.
- `backend/live_transport.py` checks official UK sources and optional licensed APIs. It does not label static event configuration as live.
- Adding another event means adding event data, not rewriting the travel engine.
- The current NSPPD event (`nsppd-uk-old-trafford-2026`) is the production example.
- `test-event-manchester` is fictional and for development only. It exists to prove the engine reads event configuration dynamically. It must not be presented as a real event.

The frontend loads available events from `GET /events` and can search them. If the public API is blocked, it falls back to same-origin `events.json` / `event.json` and can still calculate an event-adjusted route with Nominatim + OSRM. The local fallback reports live traffic as unavailable.

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
- The time breakdown is `normal + live traffic (if measured) + event adjustment + additional event delay = estimated`.
- A Leaflet map (OpenStreetMap tiles, no API key) plots origin, destination, outbound route geometry and Park & Ride sites when coordinates are available.
- The journey summary covers outbound distance, estimated time, arrival, risk and event condition, plus return estimated time, arrival, risk and day rollover.

## Live Transport Intelligence

The app distinguishes four things and will not pretend static information is live:

1. **Normal route time** — OSRM driving duration.
2. **Event model** — configured traffic-management windows and extra event delay.
3. **Verified / configured disruption** — event-store records, shown as configured, not live.
4. **Live traffic / transport information** — only when a reliable public or licensed feed returns data.

### Live data sources

| Source | What it provides here | Key required? |
| --- | --- | --- |
| OSRM public router | Normal driving time and geometry | No |
| National Highways WebTRIS | Open-data reachability check only. Traffic counts, not origin-destination speeds | No |
| TfGM travel-updates page | Reachability check only. HTML is not scraped into incidents | No |
| National Highways Road and Lane Closures API | Structured live closures when configured | Yes — `NATIONAL_HIGHWAYS_SUBSCRIPTION_KEY` |
| TfGM travel alerts API | Structured live alerts when configured | Yes — `TFGM_API_KEY` (optional `TFGM_APP_KEY`) |
| TomTom Routing | Measured live delay versus the same route without traffic | Yes — `TOMTOM_API_KEY` |

No suitable free, keyless UK source currently provides measured journey speeds for an arbitrary origin and destination. National Highways DATEX / developer-portal APIs and TfGM alert APIs require subscription keys. Until a key is configured, live speed impact is reported as **Unavailable** and the existing event-adjusted estimate is used.

## Live Parking Intelligence

Park & Ride cards keep access-time estimates separate from occupancy.

```
Ladywell Park & Ride
Drive: 115 min
Transfer: 25 min
Total access: 140 min
Availability: Unknown / No live occupancy feed
Source: TfGM car parks
Updated: checked just now
```

If an official feed later returns a state for that facility, availability becomes the source value (`Available`, `Limited` or `Full`). Spaces remaining are shown only when the feed includes a number.

### Parking data sources

| Source | What it provides | Live occupancy? |
| --- | --- | --- |
| Selected event `parking_options` | Site name, location, transfer time | No |
| OSRM | Drive distance and time from the origin | No |
| TfGM GM Park and Ride open data | Static site locations | No |
| Manchester City Council parking files | Annual space counts | No |
| `https://api.tfgm.com/odata/carparks` | Occupancy when a key is accepted | Only with `TFGM_API_KEY` |

Research notes:

- TfGM's public open-data portal no longer issues new realtime keys.
- `api.tfgm.com/odata/carparks` returns `Forbidden` without credentials.
- Council parking downloads are inventories, not occupancy feeds.
- Pages are not scraped into invented occupancy figures.

Occupancy older than 15 minutes is treated as stale and falls back to `Unknown / No live occupancy feed`. Access-time calculations continue either way. Parking sites always come from the selected event; the fictional test event uses `Test Park & Ride` only.

### Freshness

Every live transport record includes `checked_at` and a source. The UI labels the feed as `Live`, `Updated X minutes ago`, `Source` or `Unavailable`. Cached live payloads older than 15 minutes are treated as stale and are not applied to the journey estimate.

### Journey impact

When a measured live delay exists it is shown separately. The OSRM duration is never silently replaced:

```
Normal route:     123 min
Live traffic:     +18 min
Event impact:     +25 min
Estimated journey: 166 min
```

If live speed data is missing, failed or stale:

```
Normal route:     123 min
Live traffic:     Unavailable
Event impact:     +25 min
Estimated journey: 148 min
```

### Fallback

If a live source is unavailable the application keeps working, shows that live traffic data is unavailable, continues using the event-adjusted estimate, and never fabricates a live value.

## Problem being solved

Large events create congestion, road restrictions and uncertain parking. People leaving from different towns need a single place to:

- search or browse configured events
- enter any reasonable starting location
- see the event destination and traffic-management window
- get an estimated outbound and return journey
- see crowd / event-period risk
- see verified disruption records and, when available, live transport records
- compare Park & Ride options associated with that event

## Architecture

```
Browser (GitHub Pages)
    GET  /events                 (Render API, with events.json fallback)
    GET  /events/search?q=       (Render API, with local filter fallback)
    GET  /events/{event_id}      (Render API, with local event fallback)
    GET  /event                  (legacy default event)
    GET  /transport/live         (live source status)
    GET  /parking/live           (occupancy feed status)
    POST /analyze                (Render API, with Nominatim + OSRM fallback)
        -> FastAPI on Render
            -> Event store
            -> Nominatim geocoding (UK-biased)
            -> OSRM driving routes (alternatives + GeoJSON when available)
            -> Event-configured timing, disruptions and parking
            -> Live transport checks and parking occupancy checks
            -> Journey breakdown, route comparison and map payload
```

- **Frontend**: static HTML, CSS and JavaScript on GitHub Pages.
- **Backend**: FastAPI (`backend/main.py`) deployed on Render.
- **Nominatim**: geocodes any user-supplied origin (and parking sites) to coordinates. Ambiguous UK names prefer `countrycodes=gb`.
- **OSRM**: public driving router used for a *normal* route distance and duration.
- **Leaflet map**: OpenStreetMap tiles on the results page. No mapping API key is required.
- **Live transport**: `backend/live_transport.py`.
- **Park & Ride intelligence**: sites configured on the selected event, with live occupancy only when a matching official feed exists.

## Important limitations

- **Parking occupancy is live only when an official feed returns a state for that facility.** Otherwise the UI labels it `Unknown / No live occupancy feed`. Access times still work.
- **Live traffic speeds are unavailable unless a licensed API key is configured.** WebTRIS is not used as a journey-time feed.
- **Journey times without live speeds remain event-adjusted estimates:**

  `estimated_minutes = round(normal_OSRM_minutes * event_factor + extra_event_delay)`

- Configured disruption records are separate from live disruption records and from modelled travel estimates.
- Nominatim is a public geocoder and may rate-limit requests. The backend caches coordinates and retries 429 responses.
- The destination is the selected event venue, not an arbitrary second user destination.
- The test event is fictional and must not be treated as production information.
- The UI does not use green/red traffic lights because those would imply measured congestion that the default deployment does not have.

## Configuration

Do not commit secrets. Optional environment variables on Render:

| Variable | Purpose |
| --- | --- |
| `TOMTOM_API_KEY` | Enable measured live delay via TomTom routing |
| `NATIONAL_HIGHWAYS_SUBSCRIPTION_KEY` | Enable National Highways Road and Lane Closures |
| `NATIONAL_HIGHWAYS_API_KEY` | Alias for the National Highways key |
| `TFGM_API_KEY` | Enable TfGM travel-alerts and car-park occupancy APIs |
| `TFGM_APP_KEY` | Additional TfGM application key if required |

Without these keys the public app still works. Live traffic is shown as unavailable.

Register for official keys at:

- National Highways Developer Portal: https://developer.data.nationalhighways.co.uk/
- TfGM open data / developer access: https://tfgm.com/data-analytics-and-insight/open-data-portal
- TomTom developer portal, if using measured speeds

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service name, status, default event and version `1.5.0` |
| GET | `/health` | Health check |
| GET | `/events` | Available events (`from` / `to` date filters optional) |
| GET | `/events/search` | Search events by name, venue, city or country |
| GET | `/events/{event_id}` | Full configuration for one event |
| GET | `/event` | Legacy default/current event (NSPPD) |
| GET | `/transport/live` | Live source status, freshness and structured records |
| GET | `/parking/live` | Parking occupancy feed status |
| POST | `/analyze` | Geocode origin, route to selected event, layered times, crowd risk, parking, live transport |

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
PYTHONPATH=. python tests/test_event_engine.py
PYTHONPATH=. python tests/test_event_discovery.py
PYTHONPATH=. python tests/test_journey_intelligence.py
PYTHONPATH=. python tests/test_live_transport.py
PYTHONPATH=. python tests/test_parking_intelligence.py
```

Open the repository-root GitHub Pages files (`index.html`, `style.css`, `script.js`) or `frontend/index.html` with a local static server.

The frontend calls the public Render API by default:

`https://event-travel-intelligence.onrender.com`

## Deployment

- Backend: Render web service from this repository, command typically `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- After pushing backend changes, trigger a Render deploy if auto-deploy is off. The live API should report version `1.5.0` and send `Access-Control-Allow-Origin` for `https://aboladvisuals.github.io`.
- Frontend: GitHub Pages from the repository root so `/event-travel-intelligence/` serves `index.html`.
- CORS is configured in `backend/main.py` for `https://aboladvisuals.github.io` and other `*.github.io` origins.

Do not commit `.env` files, secrets or API keys.

## Future improvements

Deferred to later phases:

- Broader official occupancy coverage if TfGM or councils publish a public feed
- Persisted geocode cache beyond a single process
- User accounts
