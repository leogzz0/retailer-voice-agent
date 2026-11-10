"""Structured JSON logs + per-request latency.

Every log line carries `request_id` and `conversation_id` (from the `X-Conversation-Id`
header the agent's tools send as {{system__conversation_id}}), so a single call can be
traced across agent transcript -> tool requests -> ticketing attempts.
Request/response bodies are never logged (PII).
"""

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, Response

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
conversation_id_var: ContextVar[str | None] = ContextVar("conversation_id", default=None)

_STD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": request_id_var.get(),
            "conversation_id": conversation_id_var.get(),
        }
        out.update({k: v for k, v in record.__dict__.items() if k not in _STD_ATTRS})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


log = logging.getLogger("nopalia_api.http")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    conv = request.headers.get("x-conversation-id")
    rid_token, conv_token = request_id_var.set(rid), conversation_id_var.set(conv)
    t0 = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        duration = (time.perf_counter() - t0) * 1000
        response.headers["Server-Timing"] = f"app;dur={duration:.1f}"
        return response
    finally:
        route = request.scope.get("route")
        log.info(
            "request.completed",
            extra={
                "method": request.method,
                # Route template, not raw path: groups /orders/4721 and /orders/4730.
                "route": getattr(route, "path", request.url.path),
                "tool": getattr(route, "name", None),
                "status": status,
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            },
        )
        request_id_var.reset(rid_token)
        conversation_id_var.reset(conv_token)
