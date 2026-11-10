"""Provision the ElevenLabs workspace pieces the CLI cannot manage (ADR-0006).

Idempotent: safe to run on every deploy. It upserts, by name/label:
  1. workspace secret  `nopalia_tool_api_token`  = "Bearer <NOPALIA_TOOL_API_TOKEN>"
  2. env var (secret)  `nopalia_tool_auth`       -> that secret, in `production`
  3. env var (string)  `nopalia_api_host`        = NOPALIA_PUBLIC_HOST, in `production`
  4. knowledge base docs from knowledge_base/*.md (named after the file)
  5. webhook tools from tool_configs/*.json (by tool name)

and writes the resulting IDs to provisioned.json, which render_agent.py reads.
No secret values are printed or written to disk.

Usage (from agent/):  uv run python provision.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from elevenlabs import ElevenLabs
from elevenlabs.environment_variables.types.environment_variables_create_request_body import (
    EnvironmentVariablesCreateRequestBody_Secret,
    EnvironmentVariablesCreateRequestBody_String,
)
from elevenlabs.types import EnvironmentVariableSecretValueRequest, ToolRequestModel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENVIRONMENT = "production"

SECRET_NAME = "nopalia_tool_api_token"
AUTH_VAR = "nopalia_tool_auth"
HOST_VAR = "nopalia_api_host"
KB_PREFIX = "nopalia-"


def _require(env: dict[str, str | None], key: str, where: str) -> str:
    value = (env.get(key) or "").strip()
    if not value:
        sys.exit(f"error: {key} is empty in {where}")
    return value


def upsert_secret(client: ElevenLabs, name: str, value: str) -> str:
    existing = client.conversational_ai.secrets.list(search=name).secrets
    for s in existing:
        if s.name == name:
            client.conversational_ai.secrets.update(s.secret_id, name=name, value=value)
            print(f"secret   {name}: updated")
            return s.secret_id
    created = client.conversational_ai.secrets.create(name=name, value=value)
    print(f"secret   {name}: created")
    return created.secret_id


def upsert_env_var(client: ElevenLabs, label: str, value: str | dict[str, str]) -> str:
    is_secret = isinstance(value, dict)
    env_value = EnvironmentVariableSecretValueRequest(**value) if is_secret else value
    found = client.environment_variables.list(label=label).environment_variables
    match = next((v for v in found if v.label == label), None)
    if match:
        client.environment_variables.update(match.id, values={ENVIRONMENT: env_value})
        print(f"env var  {label}: updated")
        return match.id
    if is_secret:
        request = EnvironmentVariablesCreateRequestBody_Secret(
            label=label, values={ENVIRONMENT: env_value}
        )
    else:
        request = EnvironmentVariablesCreateRequestBody_String(
            label=label, values={ENVIRONMENT: value}
        )
    created = client.environment_variables.create(request=request)
    print(f"env var  {label}: created")
    return created.id


def upsert_kb_docs(client: ElevenLabs) -> dict[str, str]:
    existing: dict[str, str] = {}
    cursor = None
    while True:
        page = client.conversational_ai.knowledge_base.list(
            search=KB_PREFIX, page_size=100, cursor=cursor
        )
        existing.update({d.name: d.id for d in page.documents})
        if not page.has_more:
            break
        cursor = page.next_cursor

    ids: dict[str, str] = {}
    for path in sorted((HERE / "knowledge_base").glob("*.md")):
        name = KB_PREFIX + path.stem
        text = path.read_text(encoding="utf-8")
        if name in existing:
            client.conversational_ai.knowledge_base.documents.update(
                existing[name], name=name, content=text
            )
            print(f"kb doc   {name}: updated")
            ids[name] = existing[name]
        else:
            doc = client.conversational_ai.knowledge_base.documents.create_from_text(
                text=text, name=name
            )
            print(f"kb doc   {name}: created")
            ids[name] = doc.id
    return ids


def upsert_tools(client: ElevenLabs) -> dict[str, str]:
    # The CLI's `tools add` ignores an existing config file and uploads a placeholder (even
    # with --dry-run), so tools are managed here. Configs reference env vars, never secrets.
    existing = {t.tool_config.name: t.id for t in client.conversational_ai.tools.list().tools}
    ids: dict[str, str] = {}
    for path in sorted((HERE / "tool_configs").glob("*.json")):
        request = ToolRequestModel.model_validate(
            {"tool_config": json.loads(path.read_text(encoding="utf-8"))}
        )
        name = request.tool_config.name
        if name in existing:
            client.conversational_ai.tools.update(existing[name], request=request)
            print(f"tool     {name}: updated")
            ids[name] = existing[name]
        else:
            ids[name] = client.conversational_ai.tools.create(request=request).id
            print(f"tool     {name}: created")
    return ids


def main() -> None:
    agent_env = dotenv_values(HERE / ".env")
    api_env = dotenv_values(ROOT / ".env")
    api_key = _require(agent_env, "ELEVENLABS_API_KEY", "agent/.env")
    host = _require(agent_env, "NOPALIA_PUBLIC_HOST", "agent/.env")
    tool_token = _require(api_env, "NOPALIA_TOOL_API_TOKEN", ".env (run `make env`)")
    if "://" in host or "/" in host:
        sys.exit("error: NOPALIA_PUBLIC_HOST must be a bare host, e.g. x.ngrok-free.app")

    client = ElevenLabs(api_key=api_key)
    secret_id = upsert_secret(client, SECRET_NAME, f"Bearer {tool_token}")
    upsert_env_var(client, AUTH_VAR, {"secret_id": secret_id})
    upsert_env_var(client, HOST_VAR, host)
    kb = upsert_kb_docs(client)

    tools = upsert_tools(client)

    out = {"knowledge_base": kb, "tools": tools}
    (HERE / "provisioned.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("wrote provisioned.json")


if __name__ == "__main__":
    os.chdir(HERE)
    main()
