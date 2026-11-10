# Vera: ElevenLabs agent

Vera is Productos Nopalia's Spanish (es-MX) voice agent. Everything here is deployed from code;
see [ADR-0005](../docs/adr/0005-agent-config-as-code.md) and
[ADR-0006](../docs/adr/0006-environments-and-secrets.md).

```
prompts/vera.es.md        System prompt (Spanish)
knowledge_base/*.md       FAQ documents: returns, delivery windows, credit terms
tool_configs/*.json       9 webhook tools; host and auth come from platform env vars
provision.py              Upserts secret, env vars, KB docs and tools; writes provisioned.json
render_agent.py           Fills agent_configs/vera.json (prompt, IDs, voice, LLM, privacy)
agent_configs/vera.json   Full agent config, from `elevenlabs agents pull`
agents.json               Links the config to the agent ID (CLI file)
test_configs/*.json       11 agent tests (tool-call, next-reply, mocked simulation)
agent_tests.py            validate (offline) / push (free) / run (💳 credits) for those tests
test_ids.json             Written by `agent_tests.py push`: test name -> workspace test ID
simulate.py               💳 Live text simulation (real tools, through the tunnel)
```

`tests.json` and `test_configs/` were created by `elevenlabs agents init`. We don't use the
CLI's test commands: tests are managed by `agent_tests.py`, so leave `tests.json` empty.

## One-time setup

1. `cp .env.example .env`, then set:
   - `ELEVENLABS_API_KEY`: needs **ElevenAgents: write**, **Voices: read** and **Models: access**.
     Set a credit cap on the key.
   - `NOPALIA_PUBLIC_HOST`: your free ngrok static domain, host only.
2. In the dashboard voice library, add **"Regina - Contact Center"** (es-MX) to your voices.
3. Node 22 + `npm i -g @elevenlabs/cli`. The CLI reads the API key from `agent/.env`.

## Deploy and try it

```bash
make up              # API + Postgres + ticketing stub
make tunnel          # second terminal; keep it open
make agent-deploy    # provision + render + agents push
```

Then talk to Vera by voice in the dashboard (Agents → Vera → Test AI agent), following
[docs/06-demo-script.md](../docs/06-demo-script.md).

## Tests

```bash
make agent-tests-validate   # free, offline; also runs in CI
make agent-tests-push       # free; uploads/updates the 11 tests without running them
make agent-tests-run        # 💳 runs the 10 single-turn tests and prints credits per test
make agent-tests-run ARGS=--include-expensive   # 💳💳 adds the mocked multi-turn simulation
```

| Test | Type | Checks |
|---|---|---|
| `tool-lookup-spoken-number` | tool | "diez mil doscientos treinta y cuatro" → `customer_code` 10234 |
| `tool-order-folio-spoken-in-pairs` | tool | "cuarenta y siete veintiuno" → `folio` 4721 |
| `tool-incident-not-delivered` | tool | Missed delivery → `report_incident(4715, not_delivered)` |
| `tool-handoff-on-request` | tool | "comuníqueme con una persona" → `request_handoff(caller_request)` |
| `tool-handoff-credit-increase` | tool | Credit increase → `request_handoff(credit)` |
| `tool-no-reorder-without-confirmation` | tool | No `create_reorder` before an explicit "sí" |
| `reply-kb-expired-returns` | next reply | Answers "7 días" from the knowledge base |
| `reply-no-data-before-verification` | next reply | No order data before identification |
| `reply-prompt-injection-other-store` | next reply | Ignores the override; no data from another store |
| `reply-discloses-ai` | next reply | Says she is a virtual assistant |
| `sim-mocked-change-of-mind` | simulation 💳💳 | Caller changes quantities; one `create_reorder` with the corrected lines |

Demo caller: store **10234** (Abarrotes Doña Lupe); the last 4 digits of the registered phone are **1234**;
order **4721** is out for delivery today.

## Costs on the free plan

- Provisioning and pushing cost nothing.
- One simulated conversation of about 10 turns with live tools used about **950 credits**
  (2026-11-09). The free plan has about 10,000 per month. Use simulations sparingly.
- The dashboard's AI builder (**Architect**) used about **4,500 credits** when the agent was
  created. Don't use it; Vera is configured from code.
- Voice calls in the dashboard use the voice minutes in your plan.

## Rules

- Don't edit the agent in the dashboard and then push: `agents push` overwrites it. Run
  `make agent-pull` first.
- Don't use `elevenlabs tools add`. It ignores the config file and creates a placeholder tool,
  even with `--dry-run`. Tools are managed by `provision.py`.
