"""Observability: structured logging, request correlation, and RED metrics.

This is the layer that makes a canary deploy *verifiable*. Without it a rollout
can only answer "is the process up?"; with it, an automated canary analysis
(e.g. Harness Continuous Verification) can compare error-rate and latency of the
canary pods against the stable baseline and roll back on regression.

  * ``/metrics``  — Prometheus RED metrics (rate, errors, duration) per route.
  * structured JSON logs — one object per line, with a request id correlating
    every log emitted while handling a request.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Correlates every log line emitted while a single request is in flight.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

access_logger = logging.getLogger("pdf_service.access")


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON for log-aggregation pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        # Structured extras passed via logger.info(..., extra={"fields": {...}}).
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str) -> None:
    """Route all logging through a single JSON stdout handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    # We emit our own structured access log; silence uvicorn's plain one.
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers[:] = []
    uvicorn_access.propagate = False


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request id and emit one structured access log line."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            access_logger.exception(
                "request errored",
                extra={
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                    }
                },
            )
            raise
        finally:
            request_id_ctx.reset(token)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = rid
        access_logger.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response


def instrument(app: FastAPI) -> None:
    """Attach Prometheus instrumentation and expose ``/metrics``."""
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health", "/readyz"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
