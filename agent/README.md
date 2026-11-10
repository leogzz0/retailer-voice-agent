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
simulate.py               Runs a live text simulation (real tools, through the tunnel)
```

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
cd agent && uv run python simulate.py order-status   # optional live text check
```

Demo caller: store **10234** (Abarrotes Doña Lupe); the last 4 digits of the registered phone are **1234**;
order **4721** is out for delivery today.

## Costs on the free plan

- Provisioning and pushing cost nothing.
- One simulated conversation of about 10 turns with live tools used about **950 credits**
  (2026-11-09). The free plan has about 10,000 per month. Use simulations sparingly, and
  prefer the mocked tests planned for M4.
- Voice calls in the dashboard use the voice minutes in your plan.

## Rules

- Don't edit the agent in the dashboard and then push: `agents push` overwrites it. Run
  `make agent-pull` first.
- Don't use `elevenlabs tools add`. It ignores the config file and creates a placeholder tool,
  even with `--dry-run`. Tools are managed by `provision.py`.
