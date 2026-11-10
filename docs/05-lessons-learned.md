# Lessons learned

What surprised us while building the Vera pilot, and what we would do the same or differently.
Dates are 2026-11-09/10. Tool versions: ElevenLabs CLI 1.9.0, Python SDK 2.77.0.

## About the platform

1. **Check every product detail live, not from memory.** Several things differed from what we
   expected: the CLI cannot manage environment variables, secrets or the knowledge base;
   `simulate-conversation` was retired on 2026-10-31 (HTTP 410) while the SDK still exposes it;
   and the available LLM list changes often. We confirmed each one with a free read-only call before
   relying on it.
2. **`--dry-run` is not always dry.** `elevenlabs tools add --dry-run` created a real
   placeholder tool and ignored our config file. We moved tool management to the SDK and wrote
   the rule into the runbook. *Lesson:* test any write command against a scratch target first,
   and read the account back afterwards.
3. **Webhook tool errors are hidden from the LLM by default.** With `tool_error_handling_mode:
   auto`, Vera saw "HTTP 422" instead of our carefully written Spanish `message_es`. She
   recovered only because the prompt described the flow. `passthrough` fixes it. A contract
   test now enforces it.
4. **Sanitized dynamic variables make conversation-bound auth practical.** The verification token
   is assigned with `sanitize: true`. The LLM never sees it, but later tools send it as a header.
   We proved this in a live run before building more on top of it, which was the customer's #1 concern.
5. **Library voices must be added to the workspace** before an agent can use them, and that
   needs `voices_write`. We kept the key minimal and added the voice by hand once.

## About cost (free plan)

6. **Credits go fast, and not always where you expect.** One 10-turn live simulation cost about
   **950 credits**. Using the dashboard's AI builder ("Architect") while creating the agent cost
   about **4,500**. Together that's over half the monthly free allowance in one day.
   *What we'd do differently:* put a credit cap on the API key from day one, tag every command in
   docs with its cost, and **ask before anything that spends credits**. Free checks come first:
   local tests, the offline contract test, offline validation of agent tests, and reading
   configs back.
7. **Prefer single-turn tests to simulations.** Tool-call and next-reply tests check one decision
   each. Most of the confidence comes from the API's own 121 local tests and the contract test,
   which cost nothing.

## About design

8. **Pre-render everything spoken.** Dates, windows and references come from the API as Spanish
   phrases (`window_es`, `ticket_number_es`). The first live run read "INC-000002" as six digits.
   The API now returns "reporte número dos".
9. **Pin identity outside the LLM.** After verification, the store code comes from a dynamic
   variable, not from the model. A prompt injection can't switch stores, because the model never
   chooses the store.
10. **Design for the failure of your own fallback.** Handoffs go through the same API as
    everything else. If the tunnel drops, "talk to a human" fails too, so the prompt has a last
    resort that needs no tool: the call center number.
11. **Per-conversation lockouts, store-level alerts.** A store-wide lockout let anyone deny
    service to a store by guessing wrong three times. Counting per call and alerting per store
    keeps the protection without the denial-of-service risk.

## About process

12. **A skeptical customer review after each milestone found real issues every time:** the
    store lockout DoS, the unproven token passing, stale demo data, unreadable references, and the
    single point of failure in handoffs. Cheap to do, and worth keeping.
13. **Keep config as code, but let the platform own its defaults.** Pulling the agent config and
    overwriting only the fields we own (`render_agent.py`) means new platform fields survive and
    dashboard edits are visible in diffs.
