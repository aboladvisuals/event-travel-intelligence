"""Shared outbound HTTP helper with timeouts and limited retries."""

import time

import requests

from backend.settings import http_retries, http_timeout


DEFAULT_USER_AGENT = (
    "EventTravelIntelligence/1.6 "
    "(https://github.com/aboladvisuals/event-travel-intelligence)"
)


def request_get(url, headers=None, params=None, timeout=None, retries=None):
    timeout = http_timeout() if timeout is None else timeout
    retries = http_retries() if retries is None else retries
    last_error = None
    merged = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        try:
            response = requests.get(
                url,
                headers=merged,
                params=params,
                timeout=timeout,
            )
            if response.status_code == 429 or response.status_code >= 500:
                last_error = requests.HTTPError(
                    f"{response.status_code} for url: {response.url}"
                )
                time.sleep(min(4, 0.5 * (2 ** attempt)))
                continue
            return response
        except requests.RequestException as error:
            last_error = error
            time.sleep(min(4, 0.5 * (2 ** attempt)))
    if last_error:
        raise last_error
    raise requests.RequestException(f"Request failed: {url}")
