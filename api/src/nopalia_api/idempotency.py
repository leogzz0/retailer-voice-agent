"""Idempotent writes: the same Idempotency-Key + operation always yields the same response.

Why it matters here: ElevenLabs may retry a tool call on timeout, and the LLM itself may call
"create reorder" twice in one conversation. Either way the store must get ONE order.

Mechanics: the key row is inserted in the same transaction as the business write. A
concurrent duplicate blocks on the unique index until the first commits, then fails with
IntegrityError and reads the stored response. Errors (4xx) are not stored, so a caller can
fix the request (e.g. lower quantities) and retry with the same key.
"""

import hashlib
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nopalia_api.clock import now_local
from nopalia_api.errors import ToolError
from nopalia_api.models import IdempotencyKey


def _hash(scope: str, payload: BaseModel) -> str:
    canonical = json.dumps(
        {"scope": scope, "body": payload.model_dump(mode="json")}, sort_keys=True
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _replay(row: IdempotencyKey, request_hash: str) -> tuple[int, dict[str, Any], bool]:
    if row.request_hash != request_hash:
        raise ToolError(
            409,
            "idempotency_conflict",
            "Ya se registró una solicitud de este tipo en esta llamada con otros datos. "
            "Para cambios, ofrece transferir con un asesor.",
        )
    return row.response_status, row.response_body, True


def run_idempotent(
    db: Session,
    *,
    key: str,
    operation: str,
    scope: str,
    payload: BaseModel,
    action: Callable[[], tuple[int, BaseModel]],
) -> tuple[int, dict[str, Any], bool]:
    """Returns (status_code, response_body, replayed)."""
    request_hash = _hash(scope, payload)
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.key == key, IdempotencyKey.operation == operation
    )
    existing = db.scalar(stmt)
    if existing is not None:
        return _replay(existing, request_hash)

    try:
        status, response = action()  # flushes business rows; may raise ToolError
        body = response.model_dump(mode="json")
        db.add(
            IdempotencyKey(
                key=key,
                operation=operation,
                request_hash=request_hash,
                response_status=status,
                response_body=body,
                created_at=now_local(),
            )
        )
        db.commit()
        return status, body, False
    except IntegrityError:
        db.rollback()
        winner = db.scalar(stmt)
        if winner is None:  # integrity error was something else
            raise
        return _replay(winner, request_hash)
    except Exception:
        db.rollback()
        raise
