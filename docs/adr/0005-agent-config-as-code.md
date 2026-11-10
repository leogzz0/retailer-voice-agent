# ADR-0005: Agent configuration as code

- **Status:** accepted
- **Date:** 2026-11-09

## Context
Nopalia's IT team will not accept a voice agent that is only configured by clicking in a
dashboard. Every change must be reviewable in a pull request and reproducible in another
workspace. We need to decide which tool owns which part of the agent's configuration.

What we found when testing the tools on 2026-11-09 (ElevenLabs CLI 1.9.0, Python SDK 2.77.0):

- `elevenlabs agents pull` / `agents push` round-trip the full agent config as JSON and update
  an existing agent in place. They work well.
- `elevenlabs tools add <name> --config-path <file>` **ignores an existing config file**. It
  uploads a placeholder tool pointing at `https://api.example.com/webhook`.
- `--dry-run` **is not a dry run** for `tools add`. It created a real tool in the workspace before
  it failed on a path check. We deleted the tool by hand.
- The CLI has no commands for the knowledge base, workspace secrets or environment variables.
- The agent config refers to tools and knowledge base documents **by ID**. IDs are
  workspace-specific.
- `POST /v1/convai/agents/{id}/simulate-conversation` was retired on 2026-10-31 (HTTP 410). The
  SDK still exposes it. Simulations now run as saved agent tests (`/agent-testing/create` +
  `/agents/{id}/run-tests`).

## Decision
**Source files in git are the source of truth.** Each part of the configuration is owned like this:

| Part | Source of truth | Deployed by |
|---|---|---|
| System prompt | `agent/prompts/vera.es.md` | `render_agent.py` → `agents push` |
| Tools (9 webhooks) | `agent/tool_configs/*.json` | `provision.py` (SDK, upsert by name) |
| Knowledge base | `agent/knowledge_base/*.md` | `provision.py` (SDK, upsert by name) |
| Secret, env vars | root `.env` / `agent/.env` (git-ignored) | `provision.py` (see ADR-0006) |
| Voice, LLM, language, privacy | constants in `render_agent.py` | `render_agent.py` → `agents push` |
| Everything else in the agent | `agent/agent_configs/vera.json` (from `agents pull`) | `agents push` |

`provision.py` writes the workspace IDs it gets back into `agent/provisioned.json`.
`render_agent.py` sets only the fields we own on top of the pulled config. That way, fields the
platform adds later survive, and re-rendering is idempotent. `make agent-deploy` runs all three
steps.

Choices recorded here:
- **LLM `claude-haiku-5-5`.** It's fast enough for voice and good at tool calls in Spanish. The
  workspace default was `deepseek-v41-flash`.
- **TTS `eleven_v4_turbo`.** `/v1/models` lists `es` support for it.
- **Voice "Regina - Contact Center"** (es-MX, voice library, free-tier allowed). A library voice
  must be added to the workspace before an agent can use it. That needs `voices_write`, which
  our key does not have, so a person adds it once in the dashboard.
- **Knowledge base `usage_mode: prompt`.** The three documents are small, so we put them in the
  prompt instead of retrieving them (RAG).
- **`tool_error_handling_mode: passthrough` on every tool.** The default, `auto`, *hides* webhook
  errors from the LLM. In the first live run Vera saw "HTTP 422" instead of our `message_es`, and
  only recovered because the prompt describes the flow.

## Alternatives considered
- **CLI only.** It can't manage tools correctly (see above), the knowledge base, secrets or
  environment variables.
- **SDK only, including the agent.** This is possible. But `agents pull/push` gives a reviewable
  JSON file that matches the dashboard, and pulling is the easiest way to see edits someone
  made in the dashboard (`make agent-pull`).
- **Terraform.** No official ElevenLabs provider was verified. It would be too heavy for a
  workspace with one agent.

## Consequences
- One command deploys everything, and running it twice changes nothing on the second run.
- `agents push` overwrites edits made in the dashboard. The rule is: pull first
  (`make agent-pull`), or don't edit in the dashboard.
- Tool and knowledge base IDs in `provisioned.json` and `vera.json` belong to one workspace.
  A second workspace (for example staging) gets its own IDs after running `provision.py`, and its
  own `agents.json`.
- We rely on CLI behaviour that may change. Re-check `tools add` in later CLI versions before
  moving tools back to the CLI.
