# Runbook: Vera pilot

How to run, deploy, observe and fix the pilot. Commands run from the repo root unless noted.
**Rule: anything marked 💳 uses ElevenLabs credits.** The free plan has about 10,000 credits a
month, so ask before running those.

## 1. Daily start

```bash
make up                  # Postgres, API, ticketing stub (migrations run on start)
make seed                # fresh demo data, dates relative to today; do this before every demo
make tunnel              # second terminal, keep open: https://<NOPALIA_PUBLIC_HOST> -> :8000
curl https://<host>/health/ready    # {"status":"ok"} from outside = ready
```

If the laptop sleeps or the tunnel closes, **every tool fails**, handoffs included. Vera then
gives the call center number (see the prompt section "Si una herramienta falla").

## 2. Deploy the agent (free)

```bash
make agent-deploy        # provision.py -> render_agent.py -> elevenlabs agents push
```

- It's idempotent: run it after any change in `agent/` or a new tunnel domain.
- **Never edit Vera in the dashboard and then deploy.** `agents push` overwrites the dashboard.
  To keep a dashboard edit, run `make agent-pull`, move the change into the source files, and deploy.
- **Never use `elevenlabs tools add`.** It ignores the config file and creates a placeholder,
  even with `--dry-run` ([ADR-0005](adr/0005-agent-config-as-code.md)). If one appears, delete it.
- The warning "`platform_settings.guardrails.synthetic_voice.trigger_action` not persisted"
  is harmless. That field came from the dashboard pull, and we don't set it.

## 3. Tests

| Command | Cost | What |
|---|---|---|
| `make check` | free | ruff, mypy, 121 API tests, including the agent↔API contract test |
| `make agent-tests-validate` | free | Builds all 11 agent tests against the SDK models offline (also runs in CI) |
| `make agent-tests-push` | free | Creates or updates the tests in ElevenLabs without running them |
| `make agent-tests-run` | 💳 | Runs the 10 single-turn tests. Credits per test not measured yet; the report prints them |
| `make agent-tests-run ARGS=--include-expensive` | 💳💳 | Also runs the mocked multi-turn simulation |
| `cd agent && uv run python simulate.py` | 💳💳💳 | Live simulation through the tunnel. **~950 credits** measured |

Voice behavior (interruptions, noise, pronunciation) is checked by hand with the
[demo script and checklist](06-demo-script.md).

## 4. Post-call webhook (one-time, dashboard)

1. ElevenLabs → Agents settings → **Webhooks** → post-call webhook URL
   `https://<NOPALIA_PUBLIC_HOST>/webhooks/elevenlabs`, event **transcription**.
2. Copy the generated signing secret into `NOPALIA_WEBHOOK_SECRET` in the root `.env`, then
   run `make up` to restart the API.
3. After a call: `docker compose exec db psql -U nopalia -c "select conversation_id, received_at from conversations order by received_at desc limit 5;"`.
   A bad signature logs `webhook.rejected` and returns 401.

## 5. Observability

Logs are JSON lines on stdout (`make logs`). Every line has `request_id` and
`conversation_id`, so one call can be followed end to end:

```bash
docker compose logs --no-log-prefix api | grep '"conversation_id": "conv_…"'
make latency                                   # p50/p95/max per tool
```

| Event | Meaning | Action |
|---|---|---|
| `request.completed` | One tool call: route, status, `duration_ms` | p95 > 500 ms → check DB / tunnel |
| `security.verification_failures_high` | ≥ 10 failed verifications for one store in 15 min | Possible attack on that store. Call the store owner; consider blocking at the edge |
| `ticketing.*` failures / handoff `failed` | Ticketing system down after retries | `make retry-handoffs`; if still failing, page the CS lead with the list of pending callbacks |
| `webhook.rejected` | Bad signature or stale timestamp | Secret mismatch after a rotation, or a spoofing attempt |

Pending callbacks:
`docker compose exec db psql -U nopalia -c "select reference, status, attempts from handoff_requests where status <> 'sent';"`

## 6. Secret rotation

| Secret | Where | Rotate |
|---|---|---|
| `NOPALIA_TOOL_API_TOKEN` | root `.env` → ElevenLabs workspace secret | Edit `.env`, `make agent-provision`, `make up`. There's a short window of 401s between the two steps. In production, accept two tokens during rollover |
| `NOPALIA_VERIFICATION_SECRET` | root `.env` only | Edit and restart. Live calls lose verification and re-verify |
| `NOPALIA_WEBHOOK_SECRET` | `.env` + ElevenLabs webhook settings | Regenerate in the dashboard, paste, restart |
| `ELEVENLABS_API_KEY` | `agent/.env` | New key with the same permissions (ElevenAgents write, Voices read, Models access) and a credit cap, then delete the old one |

## 7. Data retention

- **Transcripts:** 30 days in ElevenLabs (`retention_days`). The local `conversations` table
  has no retention yet. In production, delete rows older than 30 days daily.
- **Idempotency keys:** keep 30 days. Production job:
  `delete from idempotency_keys where created_at < now() - interval '30 days';`
- **Verification attempts:** keep 30 days for audit, then delete the same way.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Vera: "tengo un problema con el sistema" on every tool | Tunnel or API down | `make up`, `make tunnel`, check `/health/ready` from outside |
| ngrok `ERR_NGROK_121` | Agent version too old for free accounts | `ngrok update` |
| ngrok `ERR_NGROK_3200` | Tunnel not running | `make tunnel` |
| Every tool 401 | Token in ElevenLabs ≠ `.env` | `make agent-provision` |
| Push: "voice … not found" | Library voice not added to the workspace | Dashboard → Voice Library → add "Regina - Contact Center" |
| `simulate-conversation` 410 | Endpoint retired 2026-10-31 | Use saved tests (`agent_tests.py`, `simulate.py`) |
| Order list shows strange folios (10000+) | Leftovers from earlier tests | `make seed` |
| Credits drop unexpectedly | Dashboard **Architect** / AI-assist features (≈4,500 credits on 2026-11-09) | Don't use them; Vera is configured from code |

## 9. Production notes (not deployed)

- **Migrations** run as a separate release step (a Cloud Run job, `alembic upgrade head`) before
  traffic shifts, not at container start. All migrations are additive.
- **Outbox sweep** runs every 2 minutes through Cloud Scheduler. Alert if any handoff stays
  `failed` for more than 10 minutes. A missed callback breaks the "never trap a shopkeeper" promise.
- **Holidays** aren't modeled. Add a holiday calendar table before launch (see solution design §9).
- **Concurrency.** Reorders lock the customer row. A load test of parallel reorders for one store
  is still open (M2 review point 6).
