#!/usr/bin/env python3
"""Room regression smoke: validate sessions/_regression baselines + optional API health."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGRESSION = ROOT / "sessions" / "_regression"
API = "http://127.0.0.1:8765"

SCENARIOS: dict[str, dict[str, Any]] = {
    "discuss": {
        "label": "일반 discuss",
        "check": lambda turns: any(t.get("mode") == "discuss" for t in turns)
        and not any(t.get("review_mode") for t in turns),
    },
    "review-on": {
        "label": "쟁점 검토 ON",
        "check": lambda turns: any(
            t.get("mode") == "discuss" and t.get("review_mode") is True
            for t in turns
        ),
    },
    "plan": {
        "label": "지금 정리",
        "check": lambda turns: any(
            t.get("mode") == "plan" and t.get("synthesize") is True for t in turns
        ),
    },
}

REQUIRED_RUN_KEYS = (
    "workflow_id",
    "run_schema_version",
    "topic",
    "agents",
    "status",
    "turns",
    "actions",
    "approvals",
    "executions",
)


def _load_run(folder: Path) -> dict[str, Any]:
    path = folder / "run.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing run.json: {folder}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_baseline(name: str, folder: Path) -> list[str]:
    errors: list[str] = []
    spec = SCENARIOS.get(name)
    if spec is None:
        return [f"unknown scenario folder: {name}"]

    try:
        run = _load_run(folder)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{name}: {exc}"]

    for key in REQUIRED_RUN_KEYS:
        if key not in run:
            errors.append(f"{name}: run.json missing key {key!r}")

    if run.get("run_schema_version") != 1:
        errors.append(
            f"{name}: run_schema_version expected 1, got {run.get('run_schema_version')!r}"
        )
    if run.get("workflow_id") != "room.parallel":
        errors.append(
            f"{name}: workflow_id expected 'room.parallel', got {run.get('workflow_id')!r}"
        )

    turns = run.get("turns") or []
    if not isinstance(turns, list) or not turns:
        errors.append(f"{name}: turns[] must be a non-empty list")
    elif not spec["check"](turns):
        errors.append(f"{name}: scenario check failed ({spec['label']})")

    return errors


def validate_regression_fixtures() -> tuple[int, list[str]]:
    if not REGRESSION.is_dir():
        return 1, [f"regression dir missing: {REGRESSION}"]

    errors: list[str] = []
    checked = 0
    for name in SCENARIOS:
        folder = REGRESSION / name
        if not folder.is_dir():
            errors.append(f"missing fixture folder: {folder}")
            continue
        checked += 1
        errors.extend(validate_baseline(name, folder))

    if checked == 0:
        return 1, ["no regression scenarios found"]
    return (1 if errors else 0), errors


def probe_api_health() -> tuple[int, list[str]]:
    url = f"{API}/api/health?probe_bridge=false"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, [f"API health skipped (offline): {exc}"]

    if not payload.get("ok"):
        return 1, ["API health ok=false"]
    agents = payload.get("agents") or []
    if len(agents) < 3:
        return 1, [f"API health agents expected 3+, got {len(agents)}"]
    return 0, []


def main() -> int:
    check_api = "--api" in sys.argv
    code, errors = validate_regression_fixtures()
    for err in errors:
        print(f"FAIL: {err}", file=sys.stderr)

    if code == 0:
        print(f"OK: {len(SCENARIOS)} regression baseline(s) in {REGRESSION}")

    if check_api:
        api_code, api_msgs = probe_api_health()
        for msg in api_msgs:
            print(msg, file=sys.stderr if api_code else sys.stdout)
        code = max(code, api_code)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
