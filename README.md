# Event Travel Intelligence

Public app for planning travel to a major event using routing data, configured event conditions, verified transport disruptions and Park & Ride access times.

Live frontend: https://aboladvisuals.github.io/event-travel-intelligence/

Live API: https://event-travel-intelligence.onrender.com

Current event: **NSPPD UK Prayer Conference**, Old Trafford, Manchester, 26 September 2026.

## Problem being solved

Large events create congestion, road restrictions and uncertain parking. People leaving from different towns need a single place to:

- enter any reasonable starting location
- see the current event and destination
- get an estimated outbound and return journey
- see crowd / event-period risk
- see verified disruption records
- compare Park & Ride options

The app does **not** pretend to be a live traffic-speed or live parking-occupancy product.

## Architecture

```
Browser (GitHub Pages)
    GET  /event
    POST /analyze
        -> FastAPI on Render
            -> Nominatim geocoding
            -> OSRM driving routes
            -> Event configuration
            -> Verified TfGM-attributed disruptions
            -> Park & Ride drive + transfer estimates
```

- **Frontend**: static HTML, CSS and JavaScript on GitHub Pages.
- **Backend**: FastAPI (`backend/main.py`) deployed on Render.
- **Nominatim**: geocodes any user-supplied origin (and parking sites) to coordinates.
- **OSRM**: public driving router used for a *normal* route distance and duration.
- **Event intelligence**: configured venue, date, capacity and traffic-management window.
- **Disruption intelligence**: verified records stored in `backend/event_config.py`, attributed to TfGM.
- **Park & Ride intelligence**: Ladywell, Parkway and Sale Water Park. Drive time from the origin plus a configured transfer time.

## Important limitations

- **Parking availability is currently not live occupancy data.** The UI labels this as `Unknown / No live occupancy feed`.
- **Journey times are event-adjusted estimates and are not measured live traffic speeds.** The estimate is:

  `estimated_minutes = round(normal_OSRM_minutes * event_factor + extra_event_delay)`

- Verified disruption records are separate from modelled travel estimates.
- Nominatim is a public geocoder and may rate-limit requests. The backend caches coordinates and retries 429 responses.
- The destination is the configured event venue, not an arbitrary second user destination.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | Service name, status and current event |
| GET | `/health` | Health check |
| GET | `/event` | Full event configuration, destination and verified disruptions |
| POST | `/analyze` | Geocode origin, route, event-adjusted times, crowd risk, parking, transport status |

### Example analyze payload

```json
{
  "start_location": "Leeds",
  "departure_time": "08:00",
  "return_time": "20:30"
}
```

`destination` and `event_capacity` may be sent by the frontend but the backend uses the configured event destination and capacity.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open `frontend/index.html` with a local static server, or use the GitHub Pages copy at the repository root (`index.html`, `style.css`, `script.js`).

The frontend calls the public Render API by default:

`https://event-travel-intelligence.onrender.com`

## Deployment

- Backend: Render web service from this repository, command typically `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- Frontend: GitHub Pages from the repository root so `/event-travel-intelligence/` serves `index.html`.
- CORS is enabled for `https://aboladvisuals.github.io` and other `*.github.io` origins.

Do not commit `.env` files, secrets or API keys.

## Future improvements

- A reliable live parking-occupancy source, clearly labelled as live only if the feed is real.
- Official TfGM / National Highways structured disruption APIs instead of configured records plus a status check.
- A measured traffic source if one is licensed; until then keep calling results estimates.
- Map display of the OSRM geometry.
- Persist geocode cache beyond a single process.
