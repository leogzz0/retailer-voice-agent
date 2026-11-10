"""Contract between the agent's tool configs (agent/tool_configs) and this API.

The tools are deployed to ElevenLabs separately from the API, so nothing else would notice if
a route, a path parameter or an enum value drifted. These checks run offline in CI and cost
no ElevenLabs credits.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from nopalia_api.main import app
from nopalia_api.models import HandoffReason, IncidentKind, OrderStatus

TOOL_DIR = Path(__file__).resolve().parents[2] / "agent" / "tool_configs"
HOST = "https://{{system__env_nopalia_api_host}}"
TOOLS = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(TOOL_DIR.glob("*.json"))}

# The OpenAPI document is the API's public contract (and, unlike app.routes, it lists the
# routes of included routers on every FastAPI version).
ROUTES = {
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    for method in operations
}


def _schema(tool: dict[str, Any]) -> dict[str, Any]:
    return tool["api_schema"]  # type: ignore[no-any-return]


def test_all_nine_tools_present() -> None:
    assert len(TOOLS) == 9, sorted(TOOLS)


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_tool_url_matches_an_api_route(name: str) -> None:
    api = _schema(TOOLS[name])
    assert api["url"].startswith(HOST), "host must come from the platform env var (ADR-0006)"
    path = api["url"].removeprefix(HOST)
    assert (api["method"], path) in ROUTES


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_tool_auth_comes_from_env_var_and_errors_reach_the_llm(name: str) -> None:
    tool = TOOLS[name]
    headers = _schema(tool)["request_headers"]
    assert headers["Authorization"] == {"env_var_label": "nopalia_tool_auth"}
    assert headers["X-Conversation-Id"] == {"variable_name": "system__conversation_id"}
    # The default ("auto") hides webhook errors from the LLM; our message_es must get through.
    assert tool["tool_error_handling_mode"] == "passthrough"


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_store_scoped_tools_use_the_pinned_code_and_token(name: str) -> None:
    api = _schema(TOOLS[name])
    if "/customers/{customer_code}/" not in api["url"] or name == "verify_caller":
        return
    code = api["path_params_schema"]["customer_code"]
    assert code.get("dynamic_variable") == "verified_customer_code"
    assert api["request_headers"]["X-Verification-Token"] == {"variable_name": "verification_token"}


def test_verification_token_is_hidden_from_the_llm() -> None:
    assignments = {a["dynamic_variable"]: a for a in TOOLS["verify_caller"]["assignments"]}
    assert assignments["verification_token"]["sanitize"] is True
    assert assignments["verified_customer_code"]["value_path"] == "customer_code"


@pytest.mark.parametrize(
    ("tool", "location", "field", "enum_cls"),
    [
        ("request_handoff", "request_body_schema", "reason", HandoffReason),
        ("report_incident", "request_body_schema", "kind", IncidentKind),
        ("list_recent_orders", "query_params_schema", "status", OrderStatus),
    ],
)
def test_tool_enums_match_api_enums(
    tool: str, location: str, field: str, enum_cls: type[HandoffReason]
) -> None:
    values = _schema(TOOLS[tool])[location]["properties"][field]["enum"]
    assert sorted(values) == sorted(m.value for m in enum_cls)
