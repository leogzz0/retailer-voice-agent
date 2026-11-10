"""Outbound client for the (stubbed) ticketing system, plus outbox delivery.

Resilience rules for any outbound dependency in this service:
- Explicit timeouts (connect 1s, read 2s). The default "wait forever" is never acceptable.
- Bounded retries, only on retryable failures: transport errors, timeouts, 429 and 5xx.
- Exponential backoff with full jitter, capped by an overall deadline.
- Idempotency-Key on every attempt, so a retry after a lost response can't duplicate.
"""

import logging
import random
import time
from collections.abc import Callable
from typing import Any

import httpx2 as httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from nopalia_api.clock import now_local
from nopalia_api.config import get_settings
from nopalia_api.models import HandoffRequest, HandoffStatus

log = logging.getLogger(__name__)


class TicketingUnavailable(Exception):
    pass


class TicketingClient:
    def __init__(
        self,
        client: httpx.Client,
        *,
        max_attempts: int = 3,
        base_backoff_s: float = 0.2,
        deadline_s: float = 4.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.max_attempts = max_attempts
        self.base_backoff_s = base_backoff_s
        self.deadline_s = deadline_s
        self.sleep = sleep

    def create_ticket(self, payload: dict[str, Any], idempotency_key: str) -> tuple[str, int]:
        """Returns (external_ticket_id, attempts_used)."""
        started = time.monotonic()
        last_error = "no attempts"
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.monotonic()
            try:
                r = self.client.post(
                    "/tickets", json=payload, headers={"Idempotency-Key": idempotency_key}
                )
                retryable = r.status_code == 429 or r.status_code >= 500
                if r.is_success:
                    log.info(
                        "ticketing.attempt",
                        extra={"attempt": attempt, "outcome": "ok",
                               "duration_ms": _ms(t0)},
                    )  # fmt: skip
                    return str(r.json()["ticket_id"]), attempt
                last_error = f"HTTP {r.status_code}"
                if not retryable:
                    break
            except httpx.TransportError as exc:  # includes timeouts
                last_error = type(exc).__name__
            log.warning(
                "ticketing.attempt",
                extra={"attempt": attempt, "outcome": last_error, "duration_ms": _ms(t0)},
            )
            if attempt == self.max_attempts:
                break
            backoff = random.uniform(0, self.base_backoff_s * 2 ** (attempt - 1))
            if time.monotonic() - started + backoff > self.deadline_s:
                last_error += " (deadline)"
                break
            self.sleep(backoff)
        raise TicketingUnavailable(last_error)


def _ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000, 1)


_default_client: TicketingClient | None = None


def get_ticketing_client() -> TicketingClient:
    """FastAPI dependency; tests override it with a MockTransport-backed client."""
    global _default_client
    if _default_client is None:
        s = get_settings()
        _default_client = TicketingClient(
            httpx.Client(base_url=s.ticketing_url, timeout=httpx.Timeout(2.0, connect=1.0)),
            max_attempts=s.ticketing_max_attempts,
            deadline_s=s.ticketing_deadline_s,
        )
    return _default_client


def deliver_handoff(db: Session, reference: str, client: TicketingClient) -> HandoffStatus:
    """Push one outbox row to ticketing. Safe to call repeatedly."""
    h = db.scalar(
        select(HandoffRequest).where(HandoffRequest.reference == reference).with_for_update()
    )
    if h is None or h.status is HandoffStatus.SENT:
        return HandoffStatus.SENT if h else HandoffStatus.FAILED
    payload = {
        "reference": h.reference,
        "reason": h.reason.value,
        "summary": h.summary,
        "callback_phone": h.callback_phone,
        "conversation_id": h.conversation_id,
    }
    try:
        ticket_id, attempts = client.create_ticket(payload, idempotency_key=reference)
        h.status, h.external_ticket_id, h.last_error = HandoffStatus.SENT, ticket_id, None
        h.attempts += attempts
    except TicketingUnavailable as exc:
        h.status, h.last_error = HandoffStatus.FAILED, str(exc)[:300]
        h.attempts += client.max_attempts
        log.error("handoff.delivery_failed", extra={"reference": reference, "error": str(exc)})
    h.updated_at = now_local()
    db.commit()
    return h.status


def retry_undelivered(db: Session, client: TicketingClient) -> dict[str, int]:
    """Outbox sweeper: `make retry-handoffs` (a cron/Cloud Scheduler job in production)."""
    refs = db.scalars(
        select(HandoffRequest.reference).where(
            HandoffRequest.status.in_([HandoffStatus.PENDING, HandoffStatus.FAILED])
        )
    ).all()
    result = {"sent": 0, "failed": 0}
    for ref in refs:
        if ref is not None:
            status = deliver_handoff(db, ref, client)
            result["sent" if status is HandoffStatus.SENT else "failed"] += 1
    return result


if __name__ == "__main__":
    from nopalia_api.db import get_engine

    with Session(get_engine()) as session:
        print(retry_undelivered(session, get_ticketing_client()))
