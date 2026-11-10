# ADR-0001: Run the back-office API locally and expose it via a tunnel

- **Status:** accepted
- **Date:** 2026-11-09

## Context
ElevenLabs executes server tools from its own cloud, so the API that the agent calls must be
reachable over public HTTPS. This project is a pilot and simulation with a $0 budget, and nobody
should have to operate a hosted environment for it.

## Decision
Run Postgres and the API with Docker Compose on the developer machine. Expose the API with an
**ngrok free static domain**, so the tool URLs in the agent config stay stable between sessions.

The container image is still production-shaped: non-root user, `$PORT`, migrations as a
separate concern. The runbook documents the Cloud Run + Cloud SQL path without executing it.

## Alternatives considered
- **Cloud Run + Cloud SQL:** the realistic production target for a GCP customer. Cloud SQL
  has no free tier, and it adds an environment to keep alive. Documented, not deployed.
- **Cloud Run + free hosted Postgres (Neon or Supabase):** near-zero cost, but still a hosted
  environment with credentials to manage. Not needed to show the integration.
- **Random ngrok URL per session:** free, but every restart means editing and re-pushing tool
  configs, which is error-prone.

## Consequences
- The agent only works while the laptop, Docker and the tunnel are up. That's acceptable for a demo.
- The tunnel is a public endpoint. **Tool auth (M2) is mandatory before the tunnel is ever
  opened with real tool configs**, because anyone who finds the URL could otherwise read seeded data.
- Latency numbers include the tunnel hop. Report API-side latency separately from end-to-end latency.
