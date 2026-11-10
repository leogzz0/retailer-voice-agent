"""Render agent_configs/vera.json from the sources of truth in this folder (ADR-0005).

The config file is the one `elevenlabs agents pull` wrote, so every field the platform knows
about is present. This script only sets the fields we own, so it is safe to re-run after a
pull. Then `elevenlabs agents push` deploys it.

  prompts/vera.es.md        -> system prompt
  provisioned.json          -> tool IDs and knowledge-base IDs (written by provision.py)
  constants below           -> voice, models, language, privacy

Usage (from agent/):  uv run python render_agent.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "agent_configs" / "vera.json"

LLM = "claude-haiku-5-5"  # fast, strong tool calling in Spanish; listed by /v1/convai/llm/list
TTS_MODEL = "eleven_v4_turbo"  # supports `es` per /v1/models
VOICE_ID = "9Godp7dNohUvXk6qp0gS"  # "Regina - Contact Center", es-MX voice library, free users
FIRST_MESSAGE = (
    "Hola, le atiende Vera, la asistente virtual de Productos Nopalia. "
    "¿Me da su número de cliente, por favor?"
)
ASR_KEYWORDS = ["Nopalia", "Crujis", "folio", "remisión", "abarrotes", "Vera"]
RETENTION_DAYS = 30  # transcripts hold store names and order data; see the runbook

END_CALL = {
    "type": "system",
    "name": "end_call",
    "description": (
        "End the call after saying goodbye, once the caller confirms there is nothing else, "
        "or right after a handoff has been confirmed."
    ),
    "params": {"system_tool_type": "end_call"},
}


def render(cfg: dict[str, Any]) -> dict[str, Any]:
    provisioned = json.loads((HERE / "provisioned.json").read_text(encoding="utf-8"))
    cc = cfg["conversation_config"]
    agent = cc["agent"]
    prompt = agent["prompt"]

    cfg["name"] = "Vera"
    cfg["tags"] = sorted({*cfg.get("tags", []), "nopalia", "es-MX"})

    agent["language"] = "es"
    agent["first_message"] = FIRST_MESSAGE
    # Filled by verify_caller's response assignments; empty until the caller is verified.
    agent["dynamic_variables"]["dynamic_variable_placeholders"] = {
        "verification_token": "",
        "verified_customer_code": "",
    }

    prompt["prompt"] = (HERE / "prompts" / "vera.es.md").read_text(encoding="utf-8")
    prompt["llm"] = LLM
    prompt["temperature"] = 0.2
    prompt["tool_ids"] = sorted(provisioned["tools"].values())
    prompt["tools"] = []  # tools live as standalone workspace tools, referenced by ID
    prompt["built_in_tools"]["end_call"] = END_CALL
    prompt["knowledge_base"] = [
        {"type": "text", "name": name, "id": doc_id, "usage_mode": "prompt"}
        for name, doc_id in sorted(provisioned["knowledge_base"].items())
    ]
    prompt["timezone"] = "America/Monterrey"

    cc["asr"]["keywords"] = ASR_KEYWORDS
    cc["tts"]["model_id"] = TTS_MODEL
    cc["tts"]["voice_id"] = VOICE_ID

    cfg["platform_settings"]["privacy"]["retention_days"] = RETENTION_DAYS
    return cfg


def main() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    CONFIG.write_text(
        json.dumps(render(cfg), indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"rendered {CONFIG.relative_to(HERE)}")


if __name__ == "__main__":
    main()
