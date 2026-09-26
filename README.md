# Event Travel Intelligence

Public app for planning travel to a major event using routing data, configured event conditions, verified transport disruptions, live transport checks and Park & Ride access times.

Live frontend: https://aboladvisuals.github.io/event-travel-intelligence/

Live API: https://event-travel-intelligence.onrender.com

Current production event: **NSPPD UK Prayer Conference**, Old Trafford, Manchester, 26 September 2026.

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

No suitable free, keyless UK source currently provides measured journey speeds for an arbitrary origin and destination. Until a licensed key is configured, live speed impact is reported as **Unavailable** and the existing event-adjusted estimate is used.

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

### Configuration

Do not commit secrets. Optional environment variables on Render:

| Variable | Purpose |
| --- | --- |
| `TOMTOM_API_KEY` | Enable measured live delay via TomTom routing |
| `NATIONAL_HIGHWAYS_SUBSCRIPTION_KEY` | Enable National Highways Road and Lane Closures |
| `TFGM_API_KEY` | Enable TfGM travel-alerts API |
| `TFGM_APP_KEY` | Additional TfGM application key if required |

Register at https://developer.data.nationalhighways.co.uk/ and the TfGM open data portal. Without these keys the public app still works.

## Dynamic Event Engine

Events are configuration data. Travel intelligence is a separate engine that consumes an event object.

- Event records live in `data/events/*.json`.
- `backend/live_transport.py` checks official UK sources and optional licensed APIs. It does not label static event configuration as live.
- The current NSPPD event is the production example. `test-event-manchester` is fictional / development only.

## Event Discovery

Users search or browse configured events. Selecting an event controls destination, traffic windows, disruptions, parking and `/analyze`.

## Journey Intelligence

- OSRM alternatives and geometry when returned; alternatives are never invented.
- Breakdown: `normal + live traffic (if measured) + event adjustment + additional event delay = estimated`.
- Leaflet map with OpenStreetMap tiles. No mapping API key.

## Architecture

```
Browser (GitHub Pages)
    GET  /events /events/search /events/{id} /event /transport/live
    POST /analyze
        -> FastAPI on Render
            -> Event store, Nominatim, OSRM
            -> Event model + live transport checks
            -> Journey breakdown and map payload
```

## Important limitations

- Parking availability is not live occupancy data.
- Live traffic speeds are unavailable unless a licensed API key is configured. WebTRIS is not used as a journey-time feed.
- Without live speeds, estimates remain `round(normal_OSRM_minutes * event_factor + extra_event_delay)`.
- Configured disruption records are not labelled live.
- The UI does not use green/red traffic lights without measured congestion data.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service name, status, default event and version `1.4.0` |
| GET | `/health` | Health check |
| GET | `/events` | Available events |
| GET | `/events/search` | Search events |
| GET | `/events/{event_id}` | One event |
| GET | `/event` | Legacy default event |
| GET | `/transport/live` | Live source status, freshness and structured records |
| POST | `/analyze` | Layered journey analysis including live transport |

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
```

## Deployment

- Backend: Render, `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- After pushing backend changes, trigger a Render deploy if auto-deploy is off. The live API should report version `1.4.0`.
- Frontend: GitHub Pages from the repository root.
- Do not commit `.env` files, secrets or API keys.

## Future improvements

- A reliable live parking-occupancy source, labelled live only if the feed is real
- Persist geocode cache beyond a single process
- User accounts
