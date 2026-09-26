"""Structured logging and request timing. User locations are not logged in full."""

import json
import logging
import sys
import time
import uuid

from backend.settings import APP_VERSION, log_level


def configure_logging():
    level = getattr(logging, log_level(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def log_event(logger, level, message, **fields):
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "message": message,
        "version": APP_VERSION,
    }
    payload.update(fields)
    getattr(logger, level if level in {"debug", "info", "warning", "error"} else "info")(
        json.dumps(payload, default=str)
    )


def request_id():
    return uuid.uuid4().hex[:12]


class RequestLogMiddleware:
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("eti.request")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.time()
        rid = request_id()
        status_box = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_box["code"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = int((time.time() - started) * 1000)
            path = scope.get("path")
            if path not in {"/health", "/ready"}:
                log_event(
                    self.logger,
                    "info",
                    "request",
                    request_id=rid,
                    method=scope.get("method"),
                    path=path,
                    status=status_box["code"],
                    duration_ms=duration_ms,
                )
