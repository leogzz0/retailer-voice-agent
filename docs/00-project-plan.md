# Project plan

Two-week engagement simulation, roughly 22 hours of work. Each milestone ends with a review
from the customer's engineering lead (role-played) before the next one starts.

**Constraints:** $0 budget (ElevenLabs free plan, roughly 15 voice minutes per month);
runs locally only; ngrok tunnel for ElevenLabs → local API.

| # | Milestone | Done when | Status |
|---|---|---|---|
| M0 | Discovery & project setup | Discovery summary and plan committed | ✅ |
| M1 | Customer systems API (read side) | `make up` serves seeded data; `make check` green locally and in CI | ✅ |
| M2 | Integration hardening | Tool auth, idempotent writes, signed post-call webhook, retries/timeouts, JSON logs, latency metrics, each with tests | ✅ |
| M3 | Agent as code | `elevenlabs agents push` deploys "Vera"; text chat answers an order-status question using live local data | 🔄 in review |
| M4 | Agent tests | ~10 CLI tests (happy path, unclear Spanish, mid-flow changes, handoff) passing | ⏳ |
| M5 | Customer deliverables | Solution design, runbook, exec summary, ADRs, lessons learned, demo GIF | ⏳ |

**What to cut first if behind:** the latency report script, then the demo GIF (screenshots
instead), then reduce agent tests to 6.

## Backlog (issue-sized)

Copy into GitHub Issues when convenient. Labels: `api`, `agent`, `docs`, `infra`, `security`.

### M1 — Customer systems API
- [x] `infra` Docker Compose (Postgres 16 + API), Makefile
- [x] `api` SQLAlchemy 2.0 models: customers, products, orders, order_items, deliveries
- [x] `api` Alembic initial migration incl. `pg_trgm` + `unaccent`
- [x] `api` Deterministic fictional seed data relative to today
- [x] `api` Read tools: customer lookup, recent orders, order detail, usual order, product search
- [x] `api` es-MX speech formatting for dates/windows
- [x] `infra` GitHub Actions: ruff, mypy, pytest with Postgres service, docker build
- [x] `docs` ADR-0001 local-only hosting, ADR-0002 tool API contract

### M2 — Integration hardening
- [x] `security` Bearer token auth on all `/v1` tool routes (constant-time compare, fails closed)
- [x] `security` Caller verification (caller ID or phone last 4), conversation-bound token, lockout *(from M1 review)*
- [x] `api` Delivery zones with per-zone cutoff (18:00 metro / 14:00 foráneo), no Sunday delivery *(from M1 review)*
- [x] `api` Write tools: create reorder (credit check, row lock), report delivery incident, request human callback
- [x] `api` `Idempotency-Key` support backed by a table (replay returns the original response)
- [x] `security` `POST /webhooks/elevenlabs` with HMAC verification + dedupe by `conversation_id`
- [x] `api` Outbox + outbound ticketing client with timeout, bounded retries, jittered backoff
- [x] `api` Structured JSON logs: request id, `conversation_id`, tool name, latency
- [x] `api` Latency middleware + `scripts/latency_report.py` (p50/p95 per tool)
- [x] `api` Frozen clock for tests, liveness/readiness split, configurable search threshold + ambiguity flag *(from M1 review)*
- [x] `docs` ADR-0003 integration security, ADR-0004 idempotency and outbox

### M3 — Agent as code
- [x] `agent` CLI project linked to the existing "Vera" agent (`agents pull` / `push`); Spanish system prompt
- [x] `agent` 9 webhook tools: env-var host, secret-backed auth, sanitized verification token, pinned store code
- [x] `agent` Knowledge base: returns, delivery windows, credit terms (prompt mode)
- [x] `agent` Handoff design without telephony (ticket + callback + `end_call`)
- [x] `agent` `provision.py` (secret, env vars, KB, tools) + `render_agent.py`; `make agent-deploy`
- [x] `agent` Live simulation: order 4721 status answered from local data through the tunnel *(proves M2 review point 1)*
- [x] `infra` ngrok static domain; `make tunnel`
- [x] `docs` ADR-0005 agent config as code, ADR-0006 environments and secrets
- [ ] `agent` Re-run the simulation to confirm `passthrough` error mode relays `message_es`
- [ ] `agent` Shorter spoken references (`INC-000002` was read as six digits) *(from first live run)*

### M4 — Agent tests
- [ ] `agent` Tool-call tests: identification, order status, product search params
- [ ] `agent` Next-reply tests: out-of-scope → handoff, KB answers
- [ ] `agent` Simulation tests with mocked tools: unclear numbers/dates/names, mid-flow change of mind
- [ ] `docs` Manual voice checklist for barge-in/interruptions (not testable in text)

### M5 — Customer deliverables
- [ ] `docs` Solution design, runbook, executive summary, lessons learned
- [ ] `docs` README architecture diagram (Mermaid) + demo GIF
