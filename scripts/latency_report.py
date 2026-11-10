"""Latency per tool from the API's JSON logs, plus an optional traffic generator.

  # 1) generate realistic tool traffic against the local API (needs .env for the token)
  python scripts/latency_report.py --generate 30 --env-file .env
  # 2) summarize p50/p95/max per route from logs on stdin
  docker compose logs --no-log-prefix api | python scripts/latency_report.py

Measures API-side time only (middleware start -> response). End-to-end agent latency
(STT + LLM + tool + TTS) comes from ElevenLabs conversation analytics, not from here.
"""

import argparse
import json
import statistics
import sys
import uuid
from collections import defaultdict
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(p) - 1]


def report(lines: list[str]) -> None:
    by_route: dict[str, list[float]] = defaultdict(list)
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # uvicorn startup lines, etc.
        if rec.get("event") == "request.completed" and rec.get("route", "").startswith("/v1"):
            by_route[f"{rec['method']} {rec['route']}"].append(float(rec["duration_ms"]))
    if not by_route:
        print("No /v1 request logs found.")
        return
    header = f"{'route':<52} {'n':>5} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8}"
    print(header)
    print("-" * len(header))
    for route, vals in sorted(by_route.items()):
        print(
            f"{route:<52} {len(vals):>5} {percentile(vals, 50):>8.1f} "
            f"{percentile(vals, 95):>8.1f} {max(vals):>8.1f}"
        )


def generate(n: int, base_url: str, token: str) -> None:
    import httpx2 as httpx

    conv = f"conv_load_{uuid.uuid4().hex[:8]}"
    h = {"Authorization": f"Bearer {token}", "X-Conversation-Id": conv}
    with httpx.Client(base_url=base_url, headers=h, timeout=10) as c:
        v = c.post("/v1/customers/10234/verify", json={"phone_last4": "1234"})
        v.raise_for_status()
        h2 = {"X-Verification-Token": v.json()["verification_token"]}
        for i in range(n):
            c.get("/v1/customers/lookup", params={"customer_code": "10234"})
            c.get("/v1/customers/10234/orders", headers=h2)
            c.get("/v1/customers/10234/orders/4721", headers=h2)
            c.get("/v1/customers/10234/usual-order", headers=h2)
            c.get("/v1/products/search", params={"q": ["papitas", "galletas maria"][i % 2]})
    print(f"Sent {n * 5 + 1} requests as {conv}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", type=int, default=0, help="rounds of traffic to send")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--env-file", default=".env")
    args = ap.parse_args()
    if args.generate:
        env = dict(
            line.split("=", 1)
            for line in Path(args.env_file).read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        generate(args.generate, args.base_url, env["NOPALIA_TOOL_API_TOKEN"].strip())
    else:
        report(sys.stdin.read().splitlines())


if __name__ == "__main__":
    main()
