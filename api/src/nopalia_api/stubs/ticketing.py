"""Stand-in for the customer's ticketing system (think Zendesk or a CRM queue).

Deliberately unreliable so retries are exercised in local demos:
  TICKETING_FAILURE_RATE  share of requests answered with 503 (default 0.3)
  TICKETING_LATENCY_MS    added latency per request (default 150)
Honors Idempotency-Key like a well-behaved upstream would.
"""

import itertools
import os
import random
import time
from typing import Annotated, Any

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse

app = FastAPI(title="Ticketing stub")
_tickets: dict[str, dict[str, Any]] = {}
_ids = itertools.count(1)


@app.post("/tickets")
def create_ticket(
    payload: dict[str, Any], idempotency_key: Annotated[str | None, Header()] = None
) -> JSONResponse:
    time.sleep(int(os.environ.get("TICKETING_LATENCY_MS", "150")) / 1000)
    if random.random() < float(os.environ.get("TICKETING_FAILURE_RATE", "0.3")):
        return JSONResponse({"error": "temporarily unavailable"}, status_code=503)
    if idempotency_key and idempotency_key in _tickets:
        return JSONResponse(_tickets[idempotency_key], status_code=200)
    ticket = {"ticket_id": f"ZD-{next(_ids):05d}", "received": payload}
    if idempotency_key:
        _tickets[idempotency_key] = ticket
    return JSONResponse(ticket, status_code=201)


@app.get("/tickets")
def list_tickets() -> list[dict[str, Any]]:
    return list(_tickets.values())
