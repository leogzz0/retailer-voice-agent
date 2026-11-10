# Project plan

Two-week engagement simulation, roughly 22 hours of work. Each milestone ends with a review
from the customer's engineering lead (role-played) before the next one starts.

**Constraints:** $0 budget (ElevenLabs free plan, roughly 15 voice minutes per month);
runs locally only; ngrok tunnel for ElevenLabs → local API.

| # | Milestone | Done when | Status |
|---|---|---|---|
| M0 | Discovery & project setup | Discovery summary and plan committed | ✅ |
| M1 | Customer systems API (read side) | `make up` serves seeded data; `make check` green locally and in CI | 🔄 in review |
| M2 | Integration hardening | Tool auth, idempotent writes, signed post-call webhook, retries/timeouts, JSON logs, latency metrics, each with tests | ⏳ |
| M3 | Agent as code | `elevenlabs agents push` deploys "Paty"; text chat answers an order-status question using live local data | ⏳ |
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
- [ ] `security` Bearer token auth on all `/v1` tool routes (constant-time compare)
- [ ] `api` Write tools: create reorder, report delivery incident, request human callback
- [ ] `api` `Idempotency-Key` support backed by a table (replay returns the original response)
- [ ] `security` `POST /webhooks/elevenlabs/post-call` with HMAC verification + dedupe by `conversation_id`
- [ ] `api` Outbound call to stub ticketing system with timeout + bounded retries + backoff
- [ ] `api` Structured JSON logs: request id, `conversation_id`, tool name, latency
- [ ] `api` Latency middleware + `scripts/latency_report.py` (p50/p95 per tool)

### M3 — Agent as code
- [ ] `agent` `elevenlabs agents init`; Spanish system prompt for "Paty"
- [ ] `agent` Tool configs with secret-backed auth header
- [ ] `agent` Knowledge base: returns, delivery windows, credit terms
- [ ] `agent` Handoff design without telephony (ticket + callback + end call)
- [ ] `infra` ngrok static domain; `make tunnel`
- [ ] `docs` ADR-0003 agent config as code, ADR-0004 environments without CLI support

### M4 — Agent tests
- [ ] `agent` Tool-call tests: identification, order status, product search params
- [ ] `agent` Next-reply tests: out-of-scope → handoff, KB answers
- [ ] `agent` Simulation tests with mocked tools: unclear numbers/dates/names, mid-flow change of mind
- [ ] `docs` Manual voice checklist for barge-in/interruptions (not testable in text)

### M5 — Customer deliverables
- [ ] `docs` Solution design, runbook, executive summary, lessons learned
- [ ] `docs` README architecture diagram (Mermaid) + demo GIF
