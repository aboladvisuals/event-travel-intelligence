"""Simple per-IP sliding-window limiter. Redis is not required."""

import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse

from backend.settings import (
    analyze_rate_limit,
    live_rate_limit,
    rate_limit_window,
    search_rate_limit,
)


_WINDOWS = defaultdict(deque)


def allow(bucket_key, limit, window_seconds):
    now = time.time()
    bucket = _WINDOWS[bucket_key]
    cutoff = now - window_seconds
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
        return False, retry_after, len(bucket)
    bucket.append(now)
    return True, 0, len(bucket)


def reset():
    _WINDOWS.clear()


def limit_for_path(path):
    if path == "/analyze":
        return analyze_rate_limit()
    if path.startswith("/events"):
        return search_rate_limit()
    if path in {"/transport/live", "/parking/live"}:
        return live_rate_limit()
    return None


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        limit = limit_for_path(path)
        if not limit:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        ip = client[0] if client else "unknown"
        window = rate_limit_window()
        ok, retry_after, used = allow(f"{ip}:{path}", limit, window)
        if not ok:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again shortly.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
            await response(scope, receive, send)
            return

        remaining = max(0, limit - used)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-ratelimit-limit", str(limit).encode("ascii")))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)
