# ADR-0006: Environments and secrets without CLI support

- **Status:** accepted
- **Date:** 2026-11-09

## Context
The tools must call a different base URL in each environment (an ngrok domain today, Cloud Run
in the documented production path). They also need the API bearer token, which must never
appear in git, in tool configs or in the LLM context.

ElevenLabs has **environment variables** (types `string`, `secret`, `auth_connection`), each
with one value per environment, and `production` always exists. Tool URLs reference them as
`{{system__env_<label>}}`, and headers as `{"env_var_label": "<label>"}`. A `secret` variable
points at a workspace secret. The CLI (1.9.0) cannot manage any of this. The REST API and the
Python SDK (`client.environment_variables`, `client.conversational_ai.secrets`) can.

## Decision
`agent/provision.py` upserts, by name:

- workspace secret `nopalia_tool_api_token` = `Bearer <NOPALIA_TOOL_API_TOKEN>` (read from the root `.env`);
- env var `nopalia_tool_auth` (secret) pointing at that secret;
- env var `nopalia_api_host` (string) = `NOPALIA_PUBLIC_HOST` (read from `agent/.env`).

Tool configs only contain references:

```json
"url": "https://{{system__env_nopalia_api_host}}/v1/customers/lookup",
"request_headers": { "Authorization": { "env_var_label": "nopalia_tool_auth" } }
```

We only use the `production` environment for now. A staging value would be one more key in
`values` (`{"production": ..., "staging": ...}`).

## Alternatives considered
- **Hard-code the URL and use a `secret_id` header.** This works, but every new tunnel domain or
  environment would mean editing nine files, and the IDs are workspace-specific.
- **Set these by hand in the dashboard.** Nobody can review it or reproduce it.

## Consequences
- The tool configs in git contain no secrets and no workspace IDs.
- Rotating the tool token means changing `.env`, then `make agent-provision` and restarting
  the API. The runbook covers this.
- The API key needs ElevenAgents write access. Workspace permissions were not required
  (tested 2026-11-09).
