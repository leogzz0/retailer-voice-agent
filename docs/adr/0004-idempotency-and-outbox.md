# ADR-0004: Idempotent writes and an outbox for handoffs

- **Status:** accepted
- **Date:** 2026-11-10

## Context
Discovery requirement: "the agent must not create duplicate orders if a request is retried."
In a voice agent, duplicates come from three places:
1. Platform retries after a timeout (the first request may have succeeded).
2. **The LLM calling the same tool twice**, for example after the caller says "sí, sí, confírmelo".
3. Our own retries to downstream systems (ticketing).

Separately, the human handoff must work even when the ticketing system is down. That's the moment
the caller is most frustrated.

## Decision
**Idempotency keys on every write tool** (`reorders`, `incidents`, `handoffs`):
- `Idempotency-Key` header is required. The tool config sets it to `{{system__conversation_id}}`.
- Keys are unique per `(key, operation)`. Same key with the same body returns the stored response
  with `Idempotent-Replayed: true`. Same key with a **different** body returns `409 idempotency_conflict`,
  and the agent offers a human.
- The key row is written in the same DB transaction as the business rows, so a crash can't leave one
  without the other. Concurrent duplicates serialize on the unique index.
- Errors (4xx) are not stored, so a caller can fix quantities and retry under the same key.

Using the conversation id as the key means **one reorder per call** by design. A caller who wants
to change a just-placed order gets a human. That's a product rule we confirmed fits the pilot, and it
removes the LLM double-call risk entirely.

**Outbox for handoffs:**
- The handoff row is committed first (status `pending`). The caller is promised a callback as soon as it
  commits.
- Delivery to ticketing runs **after the response** (background task). It has a 1 s connect / 2 s read
  timeout, up to 3 attempts, exponential backoff with full jitter, and a 4 s overall deadline. It retries only
  transport errors, 429 and 5xx, and sends the same `Idempotency-Key` (the handoff reference) on
  every attempt.
- Exhausted retries mark the row `failed`. `make retry-handoffs` (a scheduled job in production)
  sweeps `pending` and `failed` rows.

## Alternatives considered
- **LLM-generated request ids.** The model would need to invent and remember a UUID. That's unreliable,
  and it doesn't stop a double call with a fresh id.
- **Dedupe by content hash only (same store and same items within N minutes).** It blocks legitimate
  repeat orders, and the window is arbitrary.
- **Synchronous ticketing call inside the request.** The caller would wait up to 4 s of dead air, and an outage
  would turn into a failed handoff.
- **A message broker (Pub/Sub, Cloud Tasks).** It's the production upgrade path for the outbox sweep. That's
  overkill for a pilot with Postgres already in place.

## Consequences
- Every write tool in the agent config needs the `Idempotency-Key` header. Forgetting it is a 422,
  caught by agent tests in M4.
- The idempotency table grows with every write. It needs a retention job (keep 30 days), noted in the runbook.
- "Callback in under 30 minutes" is now a promise backed by a durable row, but **someone must
  monitor `failed` handoffs**. That's an alert in the runbook.
