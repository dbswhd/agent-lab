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


def _execs(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in run.get("executions") or [] if isinstance(row, dict)]


def _has_worktree_meta(row: dict[str, Any]) -> bool:
    return all(row.get(k) for k in ("git_root", "base_branch", "exec_branch", "worktree_path"))


def _check_worktree_merge_ok(run: dict[str, Any]) -> bool:
    rows = _execs(run)
    return any(
        row.get("status") == "merged"
        and row.get("isolation_effective") == "worktree"
        and _has_worktree_meta(row)
        and isinstance(row.get("merge"), dict)
        and row["merge"].get("commit_sha")
        for row in rows
    )


def _check_worktree_reject(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "rejected"
        and row.get("isolation_effective") == "worktree"
        for row in _execs(run)
    )


def _check_worktree_unavailable(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "blocked_isolation"
        and row.get("isolation_effective") == "block"
        and row.get("blocked_reason")
        for row in _execs(run)
    )


def _check_merge_conflict(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "merge_conflict"
        and isinstance(row.get("merge"), dict)
        and row["merge"].get("status") == "conflict"
        and bool(row["merge"].get("conflict_files"))
        for row in _execs(run)
    )


def _check_apply(run: dict[str, Any]) -> bool:
    return any(
        row.get("isolation_effective") == "apply"
        and row.get("status") in {"completed", "review_required"}
        for row in _execs(run)
    )


def _check_snapshot_override(run: dict[str, Any]) -> bool:
    return any(
        row.get("isolation_effective") == "snapshot_override"
        and row.get("status") == "pending_approval"
        and row.get("isolation_override_by") == "human"
        for row in _execs(run)
    )


def _check_pre_execute_blocked(run: dict[str, Any]) -> bool:
    return any(
        row.get("status") == "blocked_isolation"
        and isinstance(row.get("pre_verify"), dict)
        and row["pre_verify"].get("blocked") is True
        for row in _execs(run)
    )


def _check_specialist_artifact_only(run: dict[str, Any]) -> bool:
    last_turn = run.get("last_turn") or {}
    context = last_turn.get("context") or {}
    agents = context.get("agents") or []
    if not isinstance(agents, list):
        return False
    return any(
        row.get("agent") == "cursor"
        and row.get("parallel_round") == 2
        and row.get("context_mode") == "artifact_only"
        and row.get("recent_max_chars") == 1200
        and row.get("peer_suppressed") is True
        and (row.get("layer_chars") or {}).get("recent", 99999) <= 1300
        for row in agents
        if isinstance(row, dict)
    )


def _check_bridge_degraded_run(run: dict[str, Any]) -> bool:
    return any(
        t.get("mode") == "discuss" and t.get("status") == "completed"
        for t in run.get("turns") or []
        if isinstance(t, dict)
    )


def _cursor_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    agents = payload.get("agents") or []
    if not isinstance(agents, list):
        return None
    for row in agents:
        if isinstance(row, dict) and row.get("id") == "cursor":
            return row
    return None


def _check_bridge_degraded_payload(payload: dict[str, Any]) -> list[str]:
    row = _cursor_row(payload)
    if row is None:
        return ["cursor health row missing"]
    errors: list[str] = []
    if row.get("ready") is not False:
        errors.append("cursor.ready expected false")
    if row.get("degraded") is not True:
        errors.append("cursor.degraded expected true")
    if not row.get("failure_code"):
        errors.append("cursor.failure_code missing")
    fallback = str(row.get("fallback") or "")
    if "Codex/Claude" not in fallback:
        errors.append("cursor.fallback missing Codex/Claude fallback")
    remediation = row.get("remediation")
    if not isinstance(remediation, list) or not remediation:
        errors.append("cursor.remediation expected non-empty list")
    return errors


SCENARIOS: dict[str, dict[str, Any]] = {
    "discuss": {
        "label": "일반 discuss",
        "check": lambda run: any(t.get("mode") == "discuss" for t in run.get("turns") or [])
        and not any(t.get("review_mode") for t in run.get("turns") or []),
    },
    "review-on": {
        "label": "쟁점 검토 ON",
        "check": lambda run: any(
            t.get("mode") == "discuss" and t.get("review_mode") is True
            for t in run.get("turns") or []
        ),
    },
    "plan": {
        "label": "지금 정리",
        "check": lambda run: any(
            t.get("mode") == "plan" and t.get("synthesize") is True
            for t in run.get("turns") or []
        ),
    },
    "worktree_merge_ok": {
        "label": "worktree merge ok",
        "check": _check_worktree_merge_ok,
    },
    "worktree_reject": {
        "label": "worktree reject",
        "check": _check_worktree_reject,
    },
    "worktree_unavailable": {
        "label": "worktree unavailable",
        "check": _check_worktree_unavailable,
    },
    "merge_conflict": {
        "label": "merge conflict",
        "check": _check_merge_conflict,
    },
    "worktree_apply": {
        "label": "non-git apply",
        "check": _check_apply,
    },
    "snapshot_override_pending": {
        "label": "snapshot override pending",
        "check": _check_snapshot_override,
    },
    "pre_execute_blocked": {
        "label": "pre_execute blocked",
        "check": _check_pre_execute_blocked,
    },
    "specialist_r2_artifact_only": {
        "label": "specialist Cursor R2 artifact-only",
        "check": _check_specialist_artifact_only,
    },
    "bridge_degraded_health": {
        "label": "Cursor bridge degraded health shape",
        "check": _check_bridge_degraded_run,
        "expected_health": "expected_health.json",
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
    elif not spec["check"](run):
        errors.append(f"{name}: scenario check failed ({spec['label']})")

    expected_health = spec.get("expected_health")
    if expected_health:
        path = folder / str(expected_health)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {expected_health}: {exc}")
        else:
            errors.extend(f"{name}: {err}" for err in _check_bridge_degraded_payload(payload))

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

    probe_url = f"{API}/api/health?probe_bridge=true&probe_preflight=true"
    try:
        with urllib.request.urlopen(probe_url, timeout=8) as resp:
            probe_payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, [f"API bridge degraded check skipped (probe unavailable): {exc}"]

    cursor = _cursor_row(probe_payload)
    if not cursor or (cursor.get("bridge") != "error" and cursor.get("degraded") is not True):
        return 0, ["API bridge degraded check skipped (cursor bridge not degraded)"]
    shape_errors = _check_bridge_degraded_payload(probe_payload)
    if shape_errors:
        return 1, [f"API bridge degraded shape: {err}" for err in shape_errors]
    return 0, ["API bridge degraded shape OK"]


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
