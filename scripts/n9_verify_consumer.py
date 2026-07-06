#!/usr/bin/env python3
"""N9 reference consumer — external agent posts work to Agent Lab verify API.

Demonstrates the GJC-style handoff path: an external pipeline produces a diff
and optional MB-8 handoff JSON; Agent Lab returns Oracle verdict + audit headers.

Usage:
  make dev   # API on :8765
  make n9-verify-consumer

  python scripts/n9_verify_consumer.py --base http://127.0.0.1:8765 --handoff path/to/handoff.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

_AUDIT_HEADERS = (
    "X-AgentLab-Service",
    "X-AgentLab-Request-Id",
    "X-AgentLab-Oracle-Verdict",
    "X-AgentLab-Oracle-Mode",
    "X-AgentLab-Risk-Level",
)


def _post_json(url: str, payload: dict) -> tuple[dict, dict[str, str]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        headers = {k: v for k, v in resp.headers.items() if k in _AUDIT_HEADERS}
        return body, headers


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N9 verify API reference consumer")
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="Agent Lab API base URL")
    parser.add_argument(
        "--handoff",
        help="Optional GJC external_handoff JSON file (MB-8 keys)",
    )
    parser.add_argument(
        "--diff",
        default="+def helper():\n+    return 42\n",
        help="Unified diff to verify",
    )
    args = parser.parse_args(argv)

    base = args.base.rstrip("/")
    try:
        status = _get_json(f"{base}/v1/verify/status")
    except urllib.error.URLError as exc:
        print(f"verify service unreachable at {base}: {exc}", file=sys.stderr)
        print("Start API with: make dev", file=sys.stderr)
        return 1

    print(f"verify/status: oracle_mode={status.get('oracle_mode')} ok={status.get('ok')}")

    external_handoff: dict | None = None
    if args.handoff:
        external_handoff = json.loads(open(args.handoff, encoding="utf-8").read())

    payload: dict = {
        "diff": args.diff,
        "touched_paths": ["src/example.py"],
        "claim": "Add helper function",
    }
    if external_handoff:
        payload["external_handoff"] = external_handoff
        if not payload["claim"]:
            payload["claim"] = str(external_handoff.get("evidence_summary") or "")

    try:
        body, headers = _post_json(f"{base}/v1/verify", payload)
    except urllib.error.HTTPError as exc:
        print(f"POST /v1/verify failed: {exc.code} {exc.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"POST /v1/verify unreachable: {exc}", file=sys.stderr)
        return 1

    print("\n--- audit headers ---")
    for key in _AUDIT_HEADERS:
        if key in headers:
            print(f"{key}: {headers[key]}")

    print("\n--- response body (summary) ---")
    print(f"verdict: {body.get('verdict')}")
    print(f"risk_level: {body.get('risk_level')}")
    print(f"auto_approve_eligible: {body.get('auto_approve_eligible')}")
    agentlab = body.get("agentlab") or {}
    print(f"agentlab.service: {agentlab.get('service')}")
    print(f"agentlab.request_id: {agentlab.get('request_id')}")
    print(f"agentlab.oracle_mode: {agentlab.get('oracle_mode')}")

    if body.get("verdict") not in ("pass", "fail"):
        print("unexpected verdict", file=sys.stderr)
        return 1
    if headers.get("X-AgentLab-Oracle-Verdict") != body.get("verdict"):
        print("header/body verdict mismatch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
