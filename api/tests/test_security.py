"""Tool auth and caller verification."""

import logging
import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from nopalia_api.config import get_settings
from nopalia_api.security import check_verification_token, issue_verification_token

Verified = Callable[[str], dict[str, str]]

# --- 1. tool bearer token ----------------------------------------------------------------


def test_tools_reject_missing_token(anon_client: TestClient) -> None:
    r = anon_client.get("/v1/products/search", params={"q": "papitas"})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


@pytest.mark.parametrize("value", ["Bearer wrong", "test-tool-token", "Basic test-tool-token"])
def test_tools_reject_bad_token(anon_client: TestClient, value: str) -> None:
    r = anon_client.get(
        "/v1/products/search", params={"q": "papitas"}, headers={"Authorization": value}
    )
    assert r.status_code == 401


def test_health_needs_no_token(anon_client: TestClient) -> None:
    assert anon_client.get("/health/live").status_code == 200


# --- 2. caller verification --------------------------------------------------------------


def test_store_data_requires_verification(client: TestClient) -> None:
    r = client.get("/v1/customers/10234/orders/4721")
    assert r.status_code == 403
    assert r.json()["code"] == "verification_required"
    assert "cuatro dígitos" in r.json()["message_es"]


def test_verify_with_phone_last4(client: TestClient) -> None:
    r = client.post("/v1/customers/10234/verify", json={"phone_last4": "1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["customer_code"] == "10234"
    assert body["owner_first_name"] == "Guadalupe"
    assert body["credit_available_mxn"] == "16600.00"  # only revealed after verification


def test_verify_with_caller_id_needs_no_question(client: TestClient) -> None:
    r = client.post(
        "/v1/customers/10234/verify", json={}, headers={"X-Caller-Id": "+52 81 5550 1234"}
    )
    assert r.status_code == 200


def test_unresolved_caller_id_template_is_ignored(client: TestClient) -> None:
    # Web widget: no telephony, the header arrives as the literal template.
    r = client.post(
        "/v1/customers/10234/verify", json={}, headers={"X-Caller-Id": "{{system__caller_id}}"}
    )
    assert r.status_code == 422
    assert r.json()["code"] == "missing_factor"


def test_wrong_digits_then_lockout(client: TestClient, reseed: Engine) -> None:
    url = "/v1/customers/20518/verify"
    r1 = client.post(url, json={"phone_last4": "0000"})
    assert r1.status_code == 403
    assert "2 veces más" in r1.json()["message_es"]
    r2 = client.post(url, json={"phone_last4": "1111"})
    assert "1 vez más" in r2.json()["message_es"]
    client.post(url, json={"phone_last4": "2222"})
    # Even the correct digits are refused now, in THIS conversation: brute force is capped.
    r4 = client.post(url, json={"phone_last4": "2518"})
    assert r4.status_code == 429
    assert r4.json()["code"] == "verification_locked"


def test_attacker_cannot_lock_out_the_real_owner(client: TestClient, reseed: Engine) -> None:
    url = "/v1/customers/20518/verify"
    attacker = {"X-Conversation-Id": "conv_attacker"}
    for guess in ["0000", "1111", "2222"]:
        client.post(url, json={"phone_last4": guess}, headers=attacker)
    assert client.post(url, json={"phone_last4": "3333"}, headers=attacker).status_code == 429
    # The owner calls separately and verifies normally.
    owner = {"X-Conversation-Id": "conv_owner"}
    assert client.post(url, json={"phone_last4": "2518"}, headers=owner).status_code == 200


def test_many_failures_across_calls_raise_an_alert(
    client: TestClient, reseed: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    url = "/v1/customers/31007/verify"
    with caplog.at_level(logging.WARNING, logger="nopalia_api.verification"):
        for i in range(10):  # 10 different "calls", one wrong guess each
            client.post(
                url, json={"phone_last4": "0000"}, headers={"X-Conversation-Id": f"conv_bf_{i}"}
            )
    alerts = [r for r in caplog.records if r.getMessage() == "security.verification_failures_high"]
    assert len(alerts) == 1
    assert alerts[0].customer_code == "31007"  # type: ignore[attr-defined]


def test_token_for_another_store_is_rejected(client: TestClient, verified: Verified) -> None:
    r = client.get("/v1/customers/20518/orders", headers=verified("10234"))
    assert r.status_code == 403


def test_token_from_another_conversation_is_rejected(
    client: TestClient, verified: Verified
) -> None:
    headers = {**verified("10234"), "X-Conversation-Id": "conv_someone_else"}
    r = client.get("/v1/customers/10234/orders", headers=headers)
    assert r.status_code == 403


def test_expired_token_is_rejected() -> None:
    s = get_settings()
    old = issue_verification_token(s, "10234", "c1", now=time.time() - s.verification_ttl_s - 1)
    assert not check_verification_token(s, old, "10234", "c1")


def test_tampered_token_is_rejected() -> None:
    s = get_settings()
    token = issue_verification_token(s, "10234", "c1")
    exp, sig = token.split(".")
    forged = f"{int(exp) + 86400}.{sig}"  # extend expiry without re-signing
    assert not check_verification_token(s, forged, "10234", "c1")
