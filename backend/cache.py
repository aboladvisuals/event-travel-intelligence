"""Persistent cache with an in-memory layer.

SQLite is the default durable backend. Redis is used only when REDIS_URL is
set and the redis package is installed. Expired entries can still be read as
stale fallbacks so a provider outage does not drop the last good result.
"""

import json
import time

from backend import db
from backend.settings import redis_url


_MEMORY = {}
_REDIS = None
_REDIS_FAILED = False


def _redis():
    global _REDIS, _REDIS_FAILED
    if _REDIS_FAILED:
        return None
    if _REDIS is not None:
        return _REDIS
    url = redis_url()
    if not url:
        return None
    try:
        import redis  # type: ignore
    except ImportError:
        _REDIS_FAILED = True
        return None
    try:
        client = redis.Redis.from_url(url, socket_timeout=1, decode_responses=True)
        client.ping()
        _REDIS = client
        return _REDIS
    except Exception:
        _REDIS_FAILED = True
        return None


def backend_name():
    if _redis() is not None:
        return "redis"
    return "sqlite"


def cache_get(namespace, key, allow_stale=False):
    cache_key = f"{namespace}:{key}"
    now = time.time()
    memory = _MEMORY.get(cache_key)
    if memory:
        if memory["expires_at"] >= now:
            return memory["payload"], False
        if allow_stale:
            return memory["payload"], True
    client = _redis()
    if client is not None:
        raw = client.get(cache_key)
        if raw:
            try:
                payload = json.loads(raw)
                return payload, False
            except json.JSONDecodeError:
                pass
        if allow_stale:
            raw = client.get(cache_key + ":stale")
            if raw:
                try:
                    return json.loads(raw), True
                except json.JSONDecodeError:
                    pass
    row = db.get_connection().execute(
        "SELECT payload, expires_at FROM cache_entries WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()
    if not row:
        return None, False
    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError:
        return None, False
    expired = row["expires_at"] < now
    if expired and not allow_stale:
        return None, False
    _MEMORY[cache_key] = {
        "payload": payload,
        "expires_at": row["expires_at"],
        "stored_at": now,
    }
    return payload, expired


def cache_set(namespace, key, payload, ttl_seconds):
    cache_key = f"{namespace}:{key}"
    now = time.time()
    expires_at = now + int(ttl_seconds)
    _MEMORY[cache_key] = {
        "payload": payload,
        "expires_at": expires_at,
        "stored_at": now,
    }
    encoded = json.dumps(payload)
    client = _redis()
    if client is not None:
        try:
            client.setex(cache_key, max(1, int(ttl_seconds)), encoded)
            client.set(cache_key + ":stale", encoded)
        except Exception:
            pass
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO cache_entries (cache_key, namespace, payload, stored_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload=excluded.payload,
                stored_at=excluded.stored_at,
                expires_at=excluded.expires_at
            """,
            (cache_key, namespace, encoded, now, expires_at),
        )
    return payload


def cache_clear(namespace=None):
    if namespace:
        prefix = namespace + ":"
        for key in list(_MEMORY):
            if key.startswith(prefix):
                _MEMORY.pop(key, None)
        with db.cursor() as cur:
            cur.execute("DELETE FROM cache_entries WHERE namespace = ?", (namespace,))
        return
    _MEMORY.clear()
    with db.cursor() as cur:
        cur.execute("DELETE FROM cache_entries")
