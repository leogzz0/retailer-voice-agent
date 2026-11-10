"""Agent tests (M4): validate offline, upload, or run against the deployed Vera agent.

Test definitions live in test_configs/*.json (one file per test, reviewed in PRs):
  type "tool"        -> tool-call test: given the chat so far, the next tool call (or its
                        absence) and its parameters (exact / regex / LLM-judged)
  type "llm"         -> next-reply test: the next agent message is judged against a condition
  type "simulation"  -> multi-turn simulated caller; "mock_all_tools" keeps it off the API

Each file also has "cost": "low" (one agent turn) or "high" (multi-turn simulation).

Commands (from agent/):
  uv run python agent_tests.py validate      # offline, free: builds and validates every request
  uv run python agent_tests.py push          # creates/updates tests in ElevenLabs (free)
  uv run python agent_tests.py run --yes-spend-credits [--include-expensive] [--only SLUG]
                                             # runs tests: THIS USES CREDITS

Running needs `make up` + `make tunnel` only for tests without mocks (tool/llm tests do not
execute tools; they stop at the tool call or the reply).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.tests.types.tests_create_request_body import (
    TestsCreateRequestBody_Llm,
    TestsCreateRequestBody_Simulation,
    TestsCreateRequestBody_Tool,
)
from elevenlabs.types import SingleTestRunRequestModel

HERE = Path(__file__).resolve().parent
TEST_DIR = HERE / "test_configs"
IDS_FILE = HERE / "test_ids.json"
PREFIX = "vera-"
TestRequest = (
    TestsCreateRequestBody_Llm | TestsCreateRequestBody_Tool | TestsCreateRequestBody_Simulation
)


def load_specs() -> dict[str, dict[str, Any]]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(TEST_DIR.glob("*.json"))
    }


def _history(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"time_in_call_secs": i * 5, **turn} for i, turn in enumerate(turns)]


def build_request(slug: str, spec: dict[str, Any], tool_ids: dict[str, str]) -> TestRequest:
    common: dict[str, Any] = {"name": f"{PREFIX}{slug}"}
    if spec.get("dynamic_variables"):
        common["dynamic_variables"] = spec["dynamic_variables"]
    if spec.get("chat_history"):
        common["chat_history"] = _history(spec["chat_history"])

    kind = spec["type"]
    if kind == "tool":
        return TestsCreateRequestBody_Tool.model_validate(
            {
                **common,
                "tool_call_parameters": {
                    "referenced_tool": {"id": tool_ids[spec["tool_name"]], "type": "webhook"},
                    "parameters": spec.get("parameters", []),
                    "verify_absence": spec.get("verify_absence", False),
                },
            }
        )
    if kind == "llm":
        return TestsCreateRequestBody_Llm.model_validate(
            {
                **common,
                "success_condition": spec["success_condition"],
                "success_examples": [
                    {"type": "success", "response": r} for r in spec.get("success_examples", [])
                ],
                "failure_examples": [
                    {"type": "failure", "response": r} for r in spec.get("failure_examples", [])
                ],
            }
        )
    if kind == "simulation":
        mocks = spec.get("mocks", {})
        return TestsCreateRequestBody_Simulation.model_validate(
            {
                **common,
                "simulation_scenario": spec["simulation_scenario"],
                "success_condition": spec["success_condition"],
                "simulation_max_turns": spec.get("simulation_max_turns", 12),
                "tool_mock_config": {
                    "mocking_strategy": "all" if spec.get("mock_all_tools") else "none",
                    "fallback_strategy": "raise_error",
                },
                "tool_mock_overrides": {
                    tool_ids[name]: [{"mock_result": result}] for name, result in mocks.items()
                },
            }
        )
    raise ValueError(f"{slug}: unknown test type {kind!r}")


def cmd_validate(specs: dict[str, dict[str, Any]]) -> None:
    tool_names = {p.stem for p in (HERE / "tool_configs").glob("*.json")}
    fake_ids = {name: f"tool_{name}" for name in tool_names}
    for slug, spec in specs.items():
        build_request(slug, spec, fake_ids)  # raises on schema or unknown-tool errors
        print(f"ok  [{spec['cost']:>4}] {spec['type']:<10} {slug}")
    print(f"{len(specs)} tests valid (offline, no credits used)")


def _client() -> ElevenLabs:
    load_dotenv(HERE / ".env")
    return ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])


def cmd_push(specs: dict[str, dict[str, Any]]) -> None:
    client = _client()
    tool_ids = json.loads((HERE / "provisioned.json").read_text())["tools"]
    ids: dict[str, str] = {}
    for slug, spec in specs.items():
        request = build_request(slug, spec, tool_ids)
        found = client.conversational_ai.tests.list(search=request.name).tests
        match = next((t for t in found if t.name == request.name), None)
        if match:
            client.conversational_ai.tests.update(match.id, request=request)
            ids[slug] = match.id
            print(f"updated {slug}")
        else:
            ids[slug] = client.conversational_ai.tests.create(request=request).id
            print(f"created {slug}")
    IDS_FILE.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {IDS_FILE.name} (no credits used)")


def cmd_run(specs: dict[str, dict[str, Any]], include_expensive: bool, only: str | None) -> None:
    if not IDS_FILE.exists():
        sys.exit("run `agent_tests.py push` first")
    ids = json.loads(IDS_FILE.read_text())
    chosen = [
        s
        for s in specs
        if (only is None or s == only) and (include_expensive or specs[s]["cost"] == "low" or only)
    ]
    client = _client()
    agent_id = json.loads((HERE / "agents.json").read_text())["agents"][0]["id"]
    invocation = client.conversational_ai.agents.run_tests(
        agent_id, tests=[SingleTestRunRequestModel(test_id=ids[s]) for s in chosen]
    )
    print(f"running {len(chosen)} tests (invocation {invocation.id}) ...")
    for _ in range(120):
        invocation = client.conversational_ai.tests.invocations.get(invocation.id)
        if all(r.status not in ("pending", None) for r in invocation.test_runs):
            break
        time.sleep(5)
    total = 0
    for run in invocation.test_runs:
        total += run.credits_used or 0
        why = run.condition_result.rationale if run.condition_result else ""
        print(f"{run.status:<8} {run.test_name}  credits={run.credits_used}  {str(why)[:160]}")
    print(f"credits used: {total}")
    sys.exit(0 if all(r.status == "passed" for r in invocation.test_runs) else 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    sub.add_parser("push")
    run = sub.add_parser("run")
    run.add_argument("--yes-spend-credits", action="store_true")
    run.add_argument("--include-expensive", action="store_true")
    run.add_argument("--only")
    args = parser.parse_args()

    specs = load_specs()
    if args.cmd == "validate":
        cmd_validate(specs)
    elif args.cmd == "push":
        cmd_push(specs)
    else:
        if not args.yes_spend_credits:
            sys.exit(
                "Running agent tests uses ElevenLabs credits. Re-run with --yes-spend-credits."
            )
        cmd_run(specs, args.include_expensive, args.only)


if __name__ == "__main__":
    main()
