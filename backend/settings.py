"""Environment configuration. Secrets are never hardcoded."""

import os
from pathlib import Path


APP_VERSION = os.getenv("APP_VERSION", "1.6.0")
APP_NAME = "Event Travel Intelligence API"

REPO_ROOT = Path(__file__).resolve().parents[1]


def env_str(name, default=""):
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def env_int(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name, default=False):
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def env_list(name, default):
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def allowed_origins():
    return env_list(
        "ALLOWED_ORIGINS",
        [
            "https://aboladvisuals.github.io",
            "http://localhost:5500",
            "http://127.0.0.1:5500",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
    )


def allowed_origin_regex():
    return env_str("ALLOWED_ORIGIN_REGEX", r"https://.*\.github.io")


def database_path():
    configured = env_str("DATABASE_PATH")
    if configured:
        return Path(configured)
    return REPO_ROOT / "data" / "platform.sqlite"


def database_url():
    return env_str("DATABASE_URL")


def redis_url():
    return env_str("REDIS_URL")


def log_level():
    return env_str("LOG_LEVEL", "INFO").upper()


def debug_errors():
    return env_bool("DEBUG_ERRORS", False)


def http_timeout():
    return env_int("HTTP_TIMEOUT_SECONDS", 15)


def http_retries():
    return env_int("HTTP_RETRIES", 2)


def geocode_ttl():
    return env_int("GEOCODE_TTL_SECONDS", 7 * 24 * 3600)


def route_ttl():
    return env_int("ROUTE_TTL_SECONDS", 6 * 3600)


def live_ttl():
    return env_int("LIVE_TTL_SECONDS", 300)


def stale_after_minutes():
    return env_int("STALE_AFTER_MINUTES", 15)


def analyze_rate_limit():
    return env_int("ANALYZE_RATE_LIMIT", 20)


def search_rate_limit():
    return env_int("SEARCH_RATE_LIMIT", 60)


def live_rate_limit():
    return env_int("LIVE_RATE_LIMIT", 30)


def rate_limit_window():
    return env_int("RATE_LIMIT_WINDOW_SECONDS", 60)


def configured_key_flags():
    return {
        "tomtom": bool(os.getenv("TOMTOM_API_KEY")),
        "national_highways": bool(
            os.getenv("NATIONAL_HIGHWAYS_SUBSCRIPTION_KEY")
            or os.getenv("NATIONAL_HIGHWAYS_API_KEY")
        ),
        "tfgm": bool(os.getenv("TFGM_API_KEY") or os.getenv("TFGM_APP_KEY")),
    }
