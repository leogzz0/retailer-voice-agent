"""Post-call webhook (signature, replay window, dedupe) and request observability."""

import json
import logging
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from nopalia_api.models import Conversation
from nopalia_api.security import sign_webhook

SECRET = "test-webhook-secret"


def _event(conversation_id: str = "conv_abc123") -> bytes:
    return json.dumps(
        {
            "type": "post_call_transcription",
            "event_timestamp": int(time.time()),
            "data": {
                "agent_id": "agent_test",
                "conversation_id": conversation_id,
                "status": "done",
                "metadata": {"call_duration_secs": 74},
                "analysis": {"transcript_summary": "Consultó el folio 4721."},
                "transcript": [{"role": "user", "message": "¿Dónde está mi pedido?"}],
            },
        }
    ).encode()


def test_valid_webhook_is_stored_once(anon_client: TestClient, reseed: Engine) -> None:
    body = _event()
    sig = sign_webhook(SECRET, body, int(time.time()))
    first = anon_client.post(
        "/webhooks/elevenlabs", content=body, headers={"ElevenLabs-Signature": sig}
    )
    assert first.json() == {"status": "ok", "duplicate": False}
    # ElevenLabs retries deliveries: the duplicate is acknowledged, not stored again.
    second = anon_client.post(
        "/webhooks/elevenlabs", content=body, headers={"ElevenLabs-Signature": sig}
    )
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    with Session(reseed) as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 1
        conv = db.get(Conversation, "conv_abc123")
        assert conv is not None
        assert conv.call_duration_secs == 74


@pytest.mark.parametrize(
    "make_sig",
    [
        lambda b: None,  # missing
        lambda b: sign_webhook("wrong-secret", b, int(time.time())),
        lambda b: sign_webhook(SECRET, b, int(time.time()) - 3600),  # replayed, too old
        lambda b: sign_webhook(SECRET, b, int(time.time()) + 3600),  # from the future
        lambda b: "t=abc,v0=deadbeef",  # malformed
    ],
    ids=["missing", "wrong-secret", "too-old", "future", "malformed"],
)
def test_bad_signatures_rejected(anon_client: TestClient, make_sig: object) -> None:
    body = _event("conv_rejected")
    sig = make_sig(body)  # type: ignore[operator]
    headers = {"ElevenLabs-Signature": sig} if sig else {}
    r = anon_client.post("/webhooks/elevenlabs", content=body, headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_signature"


def test_body_tampering_detected(anon_client: TestClient) -> None:
    body = _event()
    sig = sign_webhook(SECRET, body, int(time.time()))
    tampered = body.replace(b"4721", b"9999")
    r = anon_client.post(
        "/webhooks/elevenlabs", content=tampered, headers={"ElevenLabs-Signature": sig}
    )
    assert r.status_code == 401


def test_other_event_types_acknowledged(anon_client: TestClient) -> None:
    body = json.dumps({"type": "post_call_audio", "data": {"conversation_id": "c"}}).encode()
    sig = sign_webhook(SECRET, body, int(time.time()))
    r = anon_client.post(
        "/webhooks/elevenlabs", content=body, headers={"ElevenLabs-Signature": sig}
    )
    assert r.json()["status"] == "ignored"


# --- observability -----------------------------------------------------------------------


def test_request_id_and_timing_headers(client: TestClient) -> None:
    r = client.get(
        "/v1/products/search", params={"q": "papitas"}, headers={"X-Request-ID": "rid-1"}
    )
    assert r.headers["X-Request-ID"] == "rid-1"
    assert r.headers["Server-Timing"].startswith("app;dur=")


def test_request_log_has_route_template_and_conversation(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="nopalia_api.http"):
        client.get("/v1/customers/lookup", params={"customer_code": "10234"})
    rec = next(r for r in caplog.records if r.getMessage() == "request.completed")
    assert rec.route == "/v1/customers/lookup"  # type: ignore[attr-defined]
    assert rec.tool == "lookup_customer"  # type: ignore[attr-defined]
    assert rec.status == 200  # type: ignore[attr-defined]
    assert rec.duration_ms >= 0  # type: ignore[attr-defined]


def test_json_formatter_includes_context() -> None:
    from nopalia_api.observability import JsonFormatter, conversation_id_var

    token = conversation_id_var.set("conv_ctx")
    try:
        record = logging.makeLogRecord({"msg": "x", "levelname": "INFO", "tool": "get_order"})
        out = json.loads(JsonFormatter().format(record))
    finally:
        conversation_id_var.reset(token)
    assert out["conversation_id"] == "conv_ctx"
    assert out["tool"] == "get_order"
