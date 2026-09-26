# Production platform (Phase 6)

This note sits beside the main README. It records the 1.6.0 platform decisions.

## Architecture

```
GitHub Pages (static UI)
    GET /events /events/search /events/{id} /event
    GET /transport/live /parking/live /health /ready
    POST /analyze
        -> FastAPI on Render
            -> JSON event catalog (source of truth)
            -> SQLite operational store (events copy, cache, source metadata)
            -> Nominatim + OSRM with persistent cache and stale fallback
            -> Event model + live transport/parking checks
```

## Database

JSON files in `data/events/` remain the reviewed catalog. Two events do not justify paid Postgres.

On startup the API syncs events, disruptions and parking locations into SQLite (`DATABASE_PATH`, default `data/platform.sqlite`; Render free uses `/tmp/eti-platform.sqlite`). Cache rows and data-source timestamps live in the same file. Set `DATABASE_URL` later if a managed database is added.

## Caching

- Geocode: 7 days
- Routes: 6 hours
- Live transport/parking: 5 minutes, with stale fallback
- Redis only if `REDIS_URL` is set and the `redis` package is installed

## Rate limits (per IP / window)

- `/analyze`: 20
- `/events*`: 60
- `/transport/live`, `/parking/live`: 30
- `/health` and `/ready` are not limited

## Observability

JSON logs with request id, method, path, status and duration. Start locations are not logged. `/health` reports version, database, cache backend and key presence. `/ready` checks the catalog and SQLite.

## Security

CORS from `ALLOWED_ORIGINS`. Analyze times must be `HH:MM`. 500 responses hide stack traces unless `DEBUG_ERRORS=true`. Secrets stay in environment variables.

## Deploy

- Build: `pip install -r backend/requirements.txt`
- Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Health: `/health`
- Rollback: redeploy the previous Render build
- Blueprint: `render.yaml`
- Example env: `.env.example`

## Tests

```
PYTHONPATH=. python tests/run_all.py
```
