#!/usr/bin/env python3
"""Validate the read-only P0 UI smoke fixture, optionally through the API."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_lab.plan_actions import parse_plan_action_sections

FIXTURE_ID = "ui_pending_diff"
FIXTURE = ROOT / "sessions" / "_regression" / FIXTURE_ID
MARKER = "P0_UI_DIFF_MARKER"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read {url}: {exc}") from exc


def validate_fixture(
    *,
    fixture: Path = FIXTURE,
    session: dict[str, Any] | None = None,
    plan_actions: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    required = ("meta.json", "topic.txt", "plan.md", "run.json")
    for name in required:
        if not (fixture / name).is_file():
            errors.append(f"missing {fixture / name}")
    if errors:
        return errors

    plan_md = (fixture / "plan.md").read_text(encoding="utf-8")
    run = _read_json(fixture / "run.json")
    topic = (fixture / "topic.txt").read_text(encoding="utf-8").strip()
    sections = parse_plan_action_sections(plan_md)
    recommended = sections.get("recommended") or {}
    pending = [
        row
        for row in run.get("executions") or []
        if isinstance(row, dict) and row.get("status") == "pending_approval"
    ]

    if topic != "P0 UI smoke · pending dry-run diff":
        errors.append("fixture topic changed")
    if recommended.get("action_key") != "now:1":
        errors.append("fixture needs executable now:1 plan action")
    if len(pending) != 1:
        errors.append("fixture needs exactly one pending_approval execution")
    else:
        row = pending[0]
        if not str(row.get("diff") or "").strip():
            errors.append("pending execution diff is empty")
        if MARKER not in str(row.get("diff") or ""):
            errors.append(f"pending execution diff missing {MARKER}")
        if not str(row.get("diff_stat") or "").strip():
            errors.append("pending execution diff_stat is empty")

    if session is not None:
        if session.get("id") != FIXTURE_ID:
            errors.append("API returned wrong fixture session")
        api_run = session.get("run") or {}
        api_pending = [
            row
            for row in api_run.get("executions") or []
            if isinstance(row, dict) and row.get("status") == "pending_approval"
        ]
        if not api_pending or MARKER not in str(api_pending[-1].get("diff") or ""):
            errors.append("API session detail does not expose pending diff marker")

    if plan_actions is not None:
        action = plan_actions.get("recommended") or {}
        if action.get("action_key") != "now:1":
            errors.append("API plan-actions does not expose now:1")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api-base",
        help="also validate the fixture served by this API base, e.g. http://127.0.0.1:8765",
    )
    args = parser.parse_args()

    session = plan_actions = None
    if args.api_base:
        base = args.api_base.rstrip("/")
        try:
            session = _fetch_json(f"{base}/api/sessions/{FIXTURE_ID}")
            plan_actions = _fetch_json(f"{base}/api/sessions/{FIXTURE_ID}/plan-actions")
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

    errors = validate_fixture(session=session, plan_actions=plan_actions)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    scope = "fixture + API" if args.api_base else "fixture"
    print(f"OK: P0 UI smoke {scope} contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
