"""Operational SQLite store.

JSON files remain the reviewed source of truth for curated events. This
database holds a queryable copy plus cache rows, source metadata and
timestamps. Postgres is not required for the current event volume.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.settings import database_path


_LOCAL = threading.local()


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    venue TEXT,
    city TEXT,
    country TEXT,
    date TEXT,
    capacity INTEGER,
    destination TEXT,
    start_time TEXT,
    end_time TEXT,
    traffic_management_start TEXT,
    traffic_management_end TEXT,
    fictional INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disruptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    type TEXT,
    start TEXT,
    end TEXT,
    impact TEXT,
    source TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parking_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    name TEXT NOT NULL,
    location TEXT,
    transfer_minutes INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_sources (
    name TEXT PRIMARY KEY,
    status TEXT,
    available INTEGER,
    note TEXT,
    checked_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_entries (
    cache_key TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    payload TEXT NOT NULL,
    stored_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_namespace ON cache_entries(namespace);
CREATE INDEX IF NOT EXISTS idx_disruptions_event ON disruptions(event_id);
CREATE INDEX IF NOT EXISTS idx_parking_event ON parking_locations(event_id);
"""


def utc_stamp():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect(path=None):
    db_path = Path(path or database_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_connection():
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = _connect()
        conn.executescript(SCHEMA)
        _LOCAL.conn = conn
    return conn


def reset_connection():
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        conn.close()
        _LOCAL.conn = None


@contextmanager
def cursor():
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def ping():
    try:
        get_connection().execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def sync_events(events):
    stamp = utc_stamp()
    with cursor() as cur:
        cur.execute("DELETE FROM disruptions")
        cur.execute("DELETE FROM parking_locations")
        for event in events:
            payload = event.model_dump() if hasattr(event, "model_dump") else dict(event)
            cur.execute(
                """
                INSERT INTO events (
                    event_id, name, venue, city, country, date, capacity,
                    destination, start_time, end_time, traffic_management_start,
                    traffic_management_end, fictional, payload, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    name=excluded.name,
                    venue=excluded.venue,
                    city=excluded.city,
                    country=excluded.country,
                    date=excluded.date,
                    capacity=excluded.capacity,
                    destination=excluded.destination,
                    start_time=excluded.start_time,
                    end_time=excluded.end_time,
                    traffic_management_start=excluded.traffic_management_start,
                    traffic_management_end=excluded.traffic_management_end,
                    fictional=excluded.fictional,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["event_id"],
                    payload["name"],
                    payload.get("venue"),
                    payload.get("city"),
                    payload.get("country"),
                    payload.get("date"),
                    payload.get("capacity"),
                    payload.get("destination"),
                    payload.get("start_time"),
                    payload.get("end_time"),
                    payload.get("traffic_management_start"),
                    payload.get("traffic_management_end"),
                    1 if payload.get("fictional") else 0,
                    json.dumps(payload),
                    stamp,
                ),
            )
            for item in payload.get("disruptions") or []:
                cur.execute(
                    """
                    INSERT INTO disruptions (
                        event_id, title, type, start, end, impact, source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["event_id"],
                        item.get("title"),
                        item.get("type"),
                        item.get("start"),
                        item.get("end"),
                        item.get("impact"),
                        item.get("source"),
                        stamp,
                    ),
                )
            for site in payload.get("parking_options") or []:
                cur.execute(
                    """
                    INSERT INTO parking_locations (
                        event_id, name, location, transfer_minutes, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        payload["event_id"],
                        site.get("name"),
                        site.get("location"),
                        site.get("transfer_minutes"),
                        stamp,
                    ),
                )


def upsert_data_source(name, status, available, note, checked_at):
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO data_sources (name, status, available, note, checked_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                status=excluded.status,
                available=excluded.available,
                note=excluded.note,
                checked_at=excluded.checked_at,
                updated_at=excluded.updated_at
            """,
            (name, status, 1 if available else 0, note, checked_at, utc_stamp()),
        )


def list_data_sources():
    rows = get_connection().execute(
        "SELECT name, status, available, note, checked_at, updated_at FROM data_sources ORDER BY name"
    ).fetchall()
    return [dict(row) for row in rows]


def event_count():
    row = get_connection().execute("SELECT COUNT(*) AS n FROM events").fetchone()
    return int(row["n"] if row else 0)


def cache_count():
    row = get_connection().execute("SELECT COUNT(*) AS n FROM cache_entries").fetchone()
    return int(row["n"] if row else 0)


def stats():
    return {
        "driver": "sqlite",
        "path": str(database_path()),
        "ok": ping(),
        "events": event_count(),
        "cache_entries": cache_count(),
        "database_url_configured": bool(database_url_configured()),
        "redis_configured": False,
    }


def database_url_configured():
    from backend.settings import database_url

    url = database_url()
    return bool(url) and not url.startswith("sqlite")
