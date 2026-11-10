"""Authentication and integrity checks. All comparisons are constant-time.

Three separate secrets, three separate jobs (see docs/adr/0003-integration-security.md):
- tool_api_token:       "this request comes from our ElevenLabs agent"     (bearer header)
- verification_secret:  "this caller proved they own store X, in this call" (signed token)
- webhook_secret:       "this webhook body was sent by ElevenLabs, unaltered" (HMAC)
"""

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import Depends, Header
from pydantic import SecretStr

from nopalia_api.config import Settings, get_settings
from nopalia_api.errors import ToolError

SettingsDep = Annotated[Settings, Depends(get_settings)]


def _require(secret: SecretStr | None, name: str) -> bytes:
    if secret is None or not secret.get_secret_value():
        # Fail closed: a missing secret must never mean "auth disabled".
        raise ToolError(503, "not_configured", f"{name} no está configurado en el servidor.")
    return secret.get_secret_value().encode()


# --- 1. tool bearer token ----------------------------------------------------------------


def require_tool_token(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = _require(settings.tool_api_token, "tool_api_token")
    scheme, _, presented = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(presented.encode(), expected):
        raise ToolError(401, "unauthorized", "Credenciales de herramienta inválidas.")


# --- 2. caller verification token --------------------------------------------------------
# Format: "<expires_unix>.<hex hmac>" over "customer_code|conversation_id|expires".
# Bound to the conversation: a token leaked from one call is useless in another.


def _verification_sig(key: bytes, customer_code: str, conversation_id: str, exp: int) -> str:
    msg = f"{customer_code}|{conversation_id}|{exp}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def issue_verification_token(
    settings: Settings, customer_code: str, conversation_id: str, now: float | None = None
) -> str:
    key = _require(settings.verification_secret, "verification_secret")
    exp = int((now or time.time()) + settings.verification_ttl_s)
    return f"{exp}.{_verification_sig(key, customer_code, conversation_id, exp)}"


def check_verification_token(
    settings: Settings, token: str, customer_code: str, conversation_id: str
) -> bool:
    key = _require(settings.verification_secret, "verification_secret")
    exp_str, _, sig = token.partition(".")
    if not exp_str.isdigit() or int(exp_str) < time.time():
        return False
    expected = _verification_sig(key, customer_code, conversation_id, int(exp_str))
    return hmac.compare_digest(sig, expected)


# --- 3. ElevenLabs webhook signature -----------------------------------------------------
# Header "ElevenLabs-Signature: t=<unix>,v0=<hex hmac_sha256(secret, f'{t}.{raw_body}')>",
# matching the official SDK's construct_event. Differences, deliberately stricter:
# constant-time compare, and reject timestamps too far in the future.


class InvalidSignature(Exception):
    pass


def verify_webhook_signature(
    settings: Settings, raw_body: bytes, header: str | None, now: float | None = None
) -> None:
    key = _require(settings.webhook_secret, "webhook_secret")
    if not header:
        raise InvalidSignature("missing signature header")
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts, sig = parts.get("t", ""), parts.get("v0", "")
    if not ts.isdigit() or not sig:
        raise InvalidSignature("malformed signature header")
    now = now or time.time()
    if int(ts) < now - settings.webhook_tolerance_s:
        raise InvalidSignature("timestamp too old")
    if int(ts) > now + settings.webhook_max_future_skew_s:
        raise InvalidSignature("timestamp in the future")
    expected = hmac.new(key, f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise InvalidSignature("signature mismatch")


def sign_webhook(secret: str, raw_body: bytes, ts: int) -> str:
    """Produce a valid header (tests, local replay script)."""
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return f"t={ts},v0={sig}"
