"""Caller verification: prove the caller belongs to the store before anything sensitive.

Factors, in order of preference:
1. Caller ID (telephony): `X-Caller-Id: {{system__caller_id}}` matches the registered phone.
   Never comes from the LLM, so a caller can't talk their way past it. (Spoofable; good
   enough for order status, not for payments.)
2. Last 4 digits of the registered phone, asked by the agent. Not printed on the delivery
   note or the storefront, unlike the customer code or the owner's name.

Brute force, without handing attackers a denial-of-service:
- N failures *in one conversation* lock verification for that conversation only
  (-> the agent offers a human). The real owner calling separately is unaffected.
- Failures *across conversations* for one store never lock it. Past a threshold they log
  `security.verification_failures_high` at WARNING for alerting. Every attempt also needs the
  tool token, so it must come through our agent: one real call or chat per few guesses.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, Header, Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nopalia_api import schemas, services, speech
from nopalia_api.clock import now_local
from nopalia_api.config import Settings, get_settings
from nopalia_api.db import get_session
from nopalia_api.errors import ToolError
from nopalia_api.models import Customer, VerificationAttempt
from nopalia_api.security import check_verification_token, issue_verification_token

log = logging.getLogger(__name__)


def _caller_id_matches(customer: Customer, caller_id: str | None) -> bool:
    # Web widget calls have no caller ID; an unresolved template arrives literally.
    if not caller_id or "{{" in caller_id:
        return False
    return services.normalize_mx_phone(caller_id) == customer.phone


def _alert_if_store_targeted(
    db: Session, settings: Settings, customer: Customer, since: datetime
) -> None:
    failed_store = (
        db.scalar(
            select(func.count()).where(
                VerificationAttempt.customer_id == customer.id,
                VerificationAttempt.success.is_(False),
                VerificationAttempt.created_at >= since,
            )
        )
        or 0
    )
    if failed_store >= settings.verification_store_alert_threshold:
        log.warning(
            "security.verification_failures_high",
            extra={"customer_code": customer.customer_code, "failures_in_window": failed_store},
        )


def verify_caller(
    db: Session,
    settings: Settings,
    customer: Customer,
    *,
    conversation_id: str,
    phone_last4: str | None,
    caller_id: str | None,
) -> schemas.VerifyOut:
    now = now_local()
    since = now - timedelta(seconds=settings.verification_window_s)
    failed_here = (
        db.scalar(
            select(func.count()).where(
                VerificationAttempt.customer_id == customer.id,
                VerificationAttempt.conversation_id == conversation_id,
                VerificationAttempt.success.is_(False),
                VerificationAttempt.created_at >= since,
            )
        )
        or 0
    )
    if failed_here >= settings.verification_max_failures:
        raise ToolError(
            429,
            "verification_locked",
            "Por seguridad no puedo verificar la cuenta en este momento. "
            "Ofrece transferir con un asesor.",
        )

    if _caller_id_matches(customer, caller_id):
        method, ok = "caller_id", True
    elif phone_last4 is not None:
        method, ok = "phone_last4", customer.phone[-4:] == phone_last4
    else:
        raise ToolError(
            422,
            "missing_factor",
            "Pide los últimos cuatro dígitos del teléfono registrado de la tienda.",
        )

    db.add(
        VerificationAttempt(
            customer_id=customer.id,
            conversation_id=conversation_id,
            method=method,
            success=ok,
            created_at=now,
        )
    )
    db.commit()

    if not ok:
        _alert_if_store_targeted(db, settings, customer, since)
        remaining = settings.verification_max_failures - failed_here - 1
        raise ToolError(
            403,
            "verification_failed",
            "Los dígitos no coinciden con el teléfono registrado. "
            + (
                f"Puede intentarlo {remaining} vez más."
                if remaining == 1
                else f"Puede intentarlo {remaining} veces más."
                if remaining > 1
                else "Ofrece transferir con un asesor."
            ),
        )
    return schemas.VerifyOut(
        verified=True,
        customer_code=customer.customer_code,
        verification_token=issue_verification_token(
            settings, customer.customer_code, conversation_id
        ),
        expires_in_s=settings.verification_ttl_s,
        store_name=customer.store_name,
        owner_first_name=speech.first_name(customer.owner_name),
        credit_available_mxn=max(
            customer.credit_limit_mxn - customer.credit_used_mxn, Decimal("0")
        ),
    )


def verified_customer(
    customer_code: Annotated[str, Path(max_length=20)],
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_conversation_id: Annotated[str, Header(min_length=1, max_length=128)],
    x_verification_token: Annotated[str | None, Header(max_length=200)] = None,
) -> Customer:
    """Dependency for every store-scoped route: valid token for THIS store and THIS call."""
    customer = services.find_customer(db, phone=None, customer_code=customer_code)
    if not x_verification_token or not check_verification_token(
        settings, x_verification_token, customer.customer_code, x_conversation_id
    ):
        raise ToolError(
            403,
            "verification_required",
            "Antes de dar información de la cuenta, verifica la identidad: "
            "pide los últimos cuatro dígitos del teléfono registrado.",
        )
    return customer
