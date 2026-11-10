"""Run a text-only simulated conversation against the deployed Vera agent.

The old /simulate-conversation endpoint was sunset on 2026-10-31; simulations now run as saved
agent tests. This script upserts a simulation test by name (tools NOT mocked: they call the
real API through the tunnel, so `make up` and `make tunnel` must be running), runs it, waits
and prints the transcript. Text only, so no voice minutes are used (LLM usage is billed).

Usage (from agent/):  uv run python simulate.py [scenario]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.tests.types.tests_create_request_body import (
    TestsCreateRequestBody_Simulation,
)
from elevenlabs.types import SingleTestRunRequestModel

HERE = Path(__file__).resolve().parent
TEST_PREFIX = "sim-live-"

SCENARIOS: dict[str, dict[str, str]] = {
    "order-status": {
        "scenario": (
            "Eres Lupe, dueña de la tienda 'Abarrotes Doña Lupe' en Monterrey. Llamas a "
            "Productos Nopalia para saber dónde está tu pedido con folio 4721. Tu número de "
            "cliente es 10234. Si te piden los últimos cuatro dígitos del teléfono de la "
            "tienda, son 1234. Hablas español mexicano, frases cortas. Cuando te digan el "
            "estado y el horario de entrega, da las gracias y despídete."
        ),
        "success": (
            "The agent verified the caller, then told her the status of order 4721 and its "
            "delivery window using data returned by the get_order tool, without inventing data."
        ),
    },
}


def upsert_test(client: ElevenLabs, name: str, spec: dict[str, str]) -> str:
    request = TestsCreateRequestBody_Simulation(
        name=name,
        simulation_scenario=spec["scenario"],
        success_condition=spec["success"],
        simulation_max_turns=12,
        tool_mock_config={"mocking_strategy": "none"},
    )
    found = client.conversational_ai.tests.list(search=name).tests
    match = next((t for t in found if t.name == name), None)
    if match:
        client.conversational_ai.tests.update(match.id, request=request)
        return match.id
    return client.conversational_ai.tests.create(request=request).id


def print_transcript(run) -> None:  # type: ignore[no-untyped-def]
    for turn in run.agent_responses or []:
        who = "VERA" if turn.role == "agent" else "USER"
        if turn.message:
            print(f"{who}: {turn.message}")
        for call in turn.tool_calls or []:
            print(f"  -> {call.tool_name} {call.params_as_json}")
        for res in turn.tool_results or []:
            body = (getattr(res, "result_value", "") or "")[:300]
            print(f"  <- {res.tool_name} error={getattr(res, 'is_error', None)} {body}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", nargs="?", default="order-status", choices=SCENARIOS)
    args = parser.parse_args()

    load_dotenv(HERE / ".env")
    agent_id = json.loads((HERE / "agents.json").read_text())["agents"][0]["id"]
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

    test_id = upsert_test(client, TEST_PREFIX + args.scenario, SCENARIOS[args.scenario])
    invocation = client.conversational_ai.agents.run_tests(
        agent_id, tests=[SingleTestRunRequestModel(test_id=test_id)]
    )
    print(f"running {TEST_PREFIX + args.scenario} (invocation {invocation.id}) ...")
    for _ in range(60):
        invocation = client.conversational_ai.tests.invocations.get(invocation.id)
        if all(r.status not in ("pending", None) for r in invocation.test_runs):
            break
        time.sleep(5)

    run = invocation.test_runs[0]
    print_transcript(run)
    cond = run.condition_result
    print(f"\nstatus: {run.status}   credits: {run.credits_used}")
    if cond:
        print(f"condition: {cond.result} - {cond.rationale}")
    sys.exit(0 if run.status == "passed" else 1)


if __name__ == "__main__":
    main()
