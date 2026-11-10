"""ElevenLabs post-call webhook receiver.

- Authenticated by HMAC signature over the RAW body (parse after verifying, never before).
- Deduplicated by conversation_id: ElevenLabs retries failed deliveries, so the same
  conversation can arrive more than once. A duplicate is acknowledged with 200, not an error,
  otherwise it would be retried again.
- Returns 200 quickly; anything heavy (analytics, QA scoring) belongs in a job, not here.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nopalia_api.clock import now_local
from nopalia_api.config import Settings, get_settings
from nopalia_api.db import get_session
from nopalia_api.errors import ToolError
from nopalia_api.models import Conversation
from nopalia_api.security import InvalidSignature, verify_webhook_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


@router.post("/elevenlabs")
async def elevenlabs_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    elevenlabs_signature: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    raw = await request.body()
    try:
        verify_webhook_signature(settings, raw, elevenlabs_signature)
    except InvalidSignature as exc:
        log.warning("webhook.rejected", extra={"reason": str(exc)})
        raise ToolError(401, "invalid_signature", "Firma inválida.") from exc

    event = json.loads(raw)
    event_type = event.get("type")
    data = event.get("data") or {}
    if event_type != "post_call_transcription":
        # post_call_audio: we don't store audio (PII, size). Failures: log for ops.
        log.info("webhook.ignored", extra={"type": event_type})
        return {"status": "ignored", "type": event_type}

    conversation_id = data.get("conversation_id")
    if not conversation_id:
        raise ToolError(400, "invalid_payload", "Falta conversation_id.")

    stmt = (
        insert(Conversation)
        .values(
            conversation_id=conversation_id,
            agent_id=data.get("agent_id"),
            status=data.get("status"),
            call_duration_secs=(data.get("metadata") or {}).get("call_duration_secs"),
            transcript_summary=(data.get("analysis") or {}).get("transcript_summary"),
            payload=event,
            received_at=now_local(),
        )
        .on_conflict_do_nothing(index_elements=["conversation_id"])
        .returning(Conversation.conversation_id)
    )
    inserted = db.execute(stmt).scalar_one_or_none() is not None
    db.commit()
    log.info(
        "webhook.post_call",
        extra={"webhook_conversation_id": conversation_id, "duplicate": not inserted},
    )
    return {"status": "ok", "duplicate": not inserted}
