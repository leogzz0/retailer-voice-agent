# ADR-0003: Three layers of integration security

- **Status:** accepted
- **Date:** 2026-11-10

## Context
The M1 review raised three points. The tunnel makes the API public. The customer code is printed on every
delivery note and storefront invoice. Nopalia requires "no shared admin credentials" and logs
correlated with calls. ElevenLabs gives us these building blocks (verified in the docs, 2026-11):

- Server-tool headers can reference **workspace secrets** and **dynamic variables**, including
  system ones such as `{{system__conversation_id}}` and `{{system__caller_id}}`.
- A tool response can **assign dynamic variables** (dot-path into the JSON) for later tool calls.
- Post-call webhooks are signed: `ElevenLabs-Signature: t=<ts>,v0=<hmac_sha256(secret, "<ts>.<body>")>`.

## Decision
Three independent checks, each with its own secret:

| Layer | Question it answers | Mechanism |
|---|---|---|
| Tool token | Is this *our agent* calling? | `Authorization: Bearer <secret>` from an ElevenLabs workspace secret; constant-time compare; **fails closed** if unset (503) |
| Caller verification | Did *this caller* prove they own *this store*, *in this call*? | `POST /verify` with caller ID (header from `{{system__caller_id}}`, never from the LLM) or last 4 digits of the registered phone. Returns an HMAC token bound to `customer_code` + `conversation_id` with a 30 min TTL. The agent stores it in a dynamic variable and sends it as `X-Verification-Token` on every store-scoped call |
| Webhook signature | Did *ElevenLabs* send this body, unaltered and recently? | HMAC over the raw body, 30 min tolerance (same as SDK), **plus** a future-skew check and constant-time compare (the SDK has neither) |

Brute force: 3 failed verifications **in one conversation** lock verification for that
conversation, and the agent offers a human. Failures across conversations never lock the store.
A store-wide lock would let anyone who has a delivery note deny service to the real owner (found
in the M2 review). Instead, 10+ failures per store in 15 minutes log
`security.verification_failures_high` for alerting. The lookup endpoint returns only store name and city, for confirmation.
Owner name and available credit appear only after verification.

## Alternatives considered
- **Owner's name as the second factor.** It's painted on the storefront. Rejected.
- **Prompt-only rules ("don't reveal data until verified").** A prompt is not a control:
  a jailbreak or a model mistake leaks data. The API enforces it.
- **Per-conversation server-side session table.** Works, but adds state and cleanup. A
  signed, conversation-bound token is stateless and expires on its own.
- **OAuth2 client credentials for the tool layer.** ElevenLabs supports it (auth connections),
  and it's the right move once the customer has an IdP-issued client. For the pilot, a rotated
  bearer secret is simpler and equally strong per request.
- **Official SDK `construct_event`.** It's correct on format, but it compares signatures with `!=`
  and accepts future timestamps. Ten lines of our own code close both gaps, and a test pins the format.

## Consequences
- **The verification token is hidden from the LLM** (confirmed 2026-11-09). `verify_caller`
  assigns it to the `verification_token` dynamic variable with `sanitize: true`. In the first
  live simulation, the tool result the LLM saw had no `verification_token` field, but
  `get_order` still sent it as `X-Verification-Token` and got a 200. The store code is pinned
  the same way (`verified_customer_code`), so after verification the LLM never chooses the store.
- Caller ID is spoofable. It's good enough for order status and reorders on credit. It's not
  enough for payments or credit-limit changes, which stay with humans.
- Three secrets to rotate. The runbook covers rotation, and only the tool token is shared with ElevenLabs.
