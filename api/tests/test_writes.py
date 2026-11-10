"""Reorders, incidents and handoffs: business rules + idempotency + outbox delivery."""

from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeTicketing
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from nopalia_api.models import DeliveryZone, HandoffRequest, HandoffStatus, Incident, Order
from nopalia_api.writes import next_delivery_date

Verified = Callable[[str], dict[str, str]]
MTY = ZoneInfo("America/Monterrey")
REORDER = {"items": [{"sku": "BOT-001", "quantity": 2}, {"sku": "BEB-001", "quantity": 5}]}


def _count(engine: Engine, model: type, **where: object) -> int:
    with Session(engine) as db:
        stmt = select(func.count()).select_from(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return db.scalar(stmt) or 0


# --- delivery date rules (pure) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "zone", "expected", "after_cutoff"),
    [
        (datetime(2026, 11, 9, 10, tzinfo=MTY), DeliveryZone.METRO, date(2026, 11, 10), False),
        (datetime(2026, 11, 9, 17, 59, tzinfo=MTY), DeliveryZone.METRO, date(2026, 11, 10), False),
        (datetime(2026, 11, 9, 18, 0, tzinfo=MTY), DeliveryZone.METRO, date(2026, 11, 11), True),
        (datetime(2026, 11, 9, 13, 0, tzinfo=MTY), DeliveryZone.FORANEO, date(2026, 11, 10), False),
        (datetime(2026, 11, 9, 15, 0, tzinfo=MTY), DeliveryZone.FORANEO, date(2026, 11, 11), True),
        # Saturday morning -> Sunday is skipped -> Monday
        (datetime(2026, 11, 14, 9, tzinfo=MTY), DeliveryZone.METRO, date(2026, 11, 16), False),
        # Friday after cutoff -> Sunday skipped -> Monday
        (datetime(2026, 11, 13, 19, tzinfo=MTY), DeliveryZone.METRO, date(2026, 11, 16), True),
    ],
)
def test_next_delivery_date(
    now: datetime, zone: DeliveryZone, expected: date, after_cutoff: bool
) -> None:
    assert next_delivery_date(now, zone) == (expected, after_cutoff)


# --- reorders ----------------------------------------------------------------------------


def test_reorder_creates_order_and_uses_credit(
    client: TestClient, verified: Verified, reseed: Engine
) -> None:
    headers = {**verified("10234"), "Idempotency-Key": "conv_test_0001"}
    r = client.post("/v1/customers/10234/reorders", json=REORDER, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["folio"] >= 10000  # from the sequence, not MAX()+1
    assert body["total_mxn"] == "1464.00"  # 2*312 + 5*168
    assert body["promised_date_es"] == "mañana, martes 10 de noviembre"
    assert body["after_cutoff"] is False
    assert body["credit_available_mxn"] == "15136.00"  # 16600 - 1464


def test_reorder_replay_returns_same_order_once(
    client: TestClient, verified: Verified, reseed: Engine
) -> None:
    headers = {**verified("10234"), "Idempotency-Key": "conv_retry_test"}
    first = client.post("/v1/customers/10234/reorders", json=REORDER, headers=headers)
    second = client.post("/v1/customers/10234/reorders", json=REORDER, headers=headers)
    assert first.json() == second.json()
    assert second.status_code == 201
    assert second.headers["Idempotent-Replayed"] == "true"
    assert _count(reseed, Order, channel="voice_agent") == 1


def test_reorder_same_key_different_body_conflicts(
    client: TestClient, verified: Verified, reseed: Engine
) -> None:
    headers = {**verified("10234"), "Idempotency-Key": "conv_change_mind"}
    client.post("/v1/customers/10234/reorders", json=REORDER, headers=headers)
    other = {"items": [{"sku": "BOT-001", "quantity": 9}]}
    r = client.post("/v1/customers/10234/reorders", json=other, headers=headers)
    assert r.status_code == 409
    assert r.json()["code"] == "idempotency_conflict"
    assert _count(reseed, Order, channel="voice_agent") == 1


def test_reorder_merges_duplicate_lines(
    client: TestClient, verified: Verified, reseed: Engine
) -> None:
    payload = {"items": [{"sku": "bot-001", "quantity": 2}, {"sku": "BOT-001", "quantity": 2}]}
    headers = {**verified("10234"), "Idempotency-Key": "conv_merge_lines"}
    r = client.post("/v1/customers/10234/reorders", json=payload, headers=headers)
    assert r.json()["total_mxn"] == "1248.00"  # 4 * 312


def test_reorder_unknown_sku(client: TestClient, verified: Verified, reseed: Engine) -> None:
    payload = {"items": [{"sku": "XXX-999", "quantity": 1}]}
    headers = {**verified("10234"), "Idempotency-Key": "conv_unknown_sku"}
    r = client.post("/v1/customers/10234/reorders", json=payload, headers=headers)
    assert r.status_code == 422
    assert r.json()["code"] == "unknown_sku"
    assert r.json()["fields"] == ["XXX-999"]


def test_reorder_over_credit_limit(client: TestClient, verified: Verified, reseed: Engine) -> None:
    payload = {"items": [{"sku": "ABA-010", "quantity": 50}]}  # 39,000 > 16,600 available
    headers = {**verified("10234"), "Idempotency-Key": "conv_too_big"}
    r = client.post("/v1/customers/10234/reorders", json=payload, headers=headers)
    assert r.status_code == 422
    assert r.json()["code"] == "credit_limit_exceeded"
    assert "16,600.00" in r.json()["message_es"]
    # Errors are not stored: the same key works once the request is fixed.
    ok = {"items": [{"sku": "ABA-010", "quantity": 2}]}
    assert client.post("/v1/customers/10234/reorders", json=ok, headers=headers).status_code == 201


def test_reorder_validation_uses_error_contract(client: TestClient, verified: Verified) -> None:
    payload = {"items": [{"sku": "BOT-001", "quantity": 0}]}
    headers = {**verified("10234"), "Idempotency-Key": "conv_bad_qty"}
    r = client.post("/v1/customers/10234/reorders", json=payload, headers=headers)
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"
    assert r.json()["fields"] == ["items.0.quantity"]


def test_reorder_requires_idempotency_key(client: TestClient, verified: Verified) -> None:
    r = client.post("/v1/customers/10234/reorders", json=REORDER, headers=verified("10234"))
    assert r.status_code == 422
    assert "idempotency-key" in r.json()["fields"][0].lower()


def test_reorder_requires_verification(client: TestClient) -> None:
    r = client.post(
        "/v1/customers/10234/reorders", json=REORDER, headers={"Idempotency-Key": "conv_x_1234"}
    )
    assert r.status_code == 403


# --- incidents ---------------------------------------------------------------------------


def test_report_incident(client: TestClient, verified: Verified, reseed: Engine) -> None:
    payload = {"folio": 4715, "kind": "not_delivered", "description": "Nadie llegó ayer"}
    headers = {**verified("10234"), "Idempotency-Key": "conv_incident_1"}
    r = client.post("/v1/customers/10234/incidents", json=payload, headers=headers)
    assert r.status_code == 201
    assert r.json()["ticket_number"].startswith("INC-")
    assert r.json()["ticket_number_es"].startswith("reporte número ")
    assert "cero, cero" not in r.json()["ticket_number_es"]
    again = client.post("/v1/customers/10234/incidents", json=payload, headers=headers)
    assert again.json()["ticket_number"] == r.json()["ticket_number"]
    assert _count(reseed, Incident) == 1


def test_incident_on_another_stores_order(
    client: TestClient, verified: Verified, reseed: Engine
) -> None:
    payload = {"folio": 4715, "kind": "damaged", "description": "Llegó roto"}
    headers = {**verified("20518"), "Idempotency-Key": "conv_incident_2"}
    r = client.post("/v1/customers/20518/incidents", json=payload, headers=headers)
    assert r.status_code == 404


# --- handoffs (outbox + retries) ---------------------------------------------------------

HANDOFF = {
    "reason": "credit",
    "summary": "Quiere aumentar su línea de crédito",
    "customer_code": "10234",
}


def _handoff(engine: Engine, ref: str) -> HandoffRequest:
    with Session(engine) as db:
        h = db.scalar(select(HandoffRequest).where(HandoffRequest.reference == ref))
        assert h is not None
        return h


def test_handoff_delivered_to_ticketing(
    client: TestClient, reseed: Engine, ticketing: FakeTicketing
) -> None:
    r = client.post("/v1/handoffs", json=HANDOFF, headers={"Idempotency-Key": "conv_h_ok"})
    assert r.status_code == 202
    assert "30 minutos" in r.json()["message_es"]
    h = _handoff(reseed, r.json()["reference"])
    assert h.status is HandoffStatus.SENT
    assert h.callback_phone == "+528155501234"  # from the store record, never returned
    assert "callback_phone" not in r.json()
    assert ticketing.requests[0].headers["Idempotency-Key"] == r.json()["reference"]


def test_handoff_retries_transient_failures(
    client: TestClient, reseed: Engine, ticketing: FakeTicketing
) -> None:
    ticketing.script = [503, "timeout", "ok"]
    r = client.post("/v1/handoffs", json=HANDOFF, headers={"Idempotency-Key": "conv_h_retry"})
    h = _handoff(reseed, r.json()["reference"])
    assert h.status is HandoffStatus.SENT
    assert h.attempts == 3
    # Same idempotency key on every attempt: upstream can dedupe.
    assert len({req.headers["Idempotency-Key"] for req in ticketing.requests}) == 1


def test_handoff_does_not_retry_client_errors(
    client: TestClient, reseed: Engine, ticketing: FakeTicketing
) -> None:
    ticketing.script = [400]
    r = client.post("/v1/handoffs", json=HANDOFF, headers={"Idempotency-Key": "conv_h_400"})
    assert len(ticketing.requests) == 1
    assert _handoff(reseed, r.json()["reference"]).status is HandoffStatus.FAILED


def test_handoff_promised_even_when_ticketing_is_down(
    client: TestClient, reseed: Engine, ticketing: FakeTicketing
) -> None:
    ticketing.script = [503, 503, 503]
    r = client.post("/v1/handoffs", json=HANDOFF, headers={"Idempotency-Key": "conv_h_down"})
    assert r.status_code == 202  # the caller is not punished for our outage
    h = _handoff(reseed, r.json()["reference"])
    assert h.status is HandoffStatus.FAILED
    assert h.last_error == "HTTP 503"


def test_handoff_for_unidentified_caller(
    client: TestClient, reseed: Engine, ticketing: FakeTicketing
) -> None:
    payload = {
        "reason": "verification_failed",
        "summary": "No pudo verificar su cuenta",
        "callback_phone": "81 1234 0000",
    }
    r = client.post("/v1/handoffs", json=payload, headers={"Idempotency-Key": "conv_h_anon"})
    assert r.status_code == 202
    h = _handoff(reseed, r.json()["reference"])
    assert h.customer_id is None
    assert h.callback_phone == "+528112340000"


def test_handoff_replay_creates_one_ticket(
    client: TestClient, reseed: Engine, ticketing: FakeTicketing
) -> None:
    headers = {"Idempotency-Key": "conv_h_twice"}
    a = client.post("/v1/handoffs", json=HANDOFF, headers=headers)
    b = client.post("/v1/handoffs", json=HANDOFF, headers=headers)
    assert a.json()["reference"] == b.json()["reference"]
    assert a.json()["reference_es"] == b.json()["reference_es"]
    assert a.json()["reference_es"].startswith("referencia número ")
    assert _count(reseed, HandoffRequest) == 1
    assert len(ticketing.requests) == 1  # already SENT: background delivery is a no-op
