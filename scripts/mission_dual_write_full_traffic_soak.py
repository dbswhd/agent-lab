"""Full-traffic soak: N Room turns (mock) → live API plan/approve.

Hits the dedicated uvicorn process (AGENT_LAB_MISSION_DUAL_WRITE=1).
Does not retire legacy writers.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src", ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SAMPLE_PLAN = """# Full-traffic soak feature

## 지금 실행

1. Add soak marker
   - 무엇을: implement soak marker
   - 어디서: `src/soak_marker.py`
   - 검증: `true`
"""


def _http_json(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw.strip() else {"detail": raw[:300]}
        except json.JSONDecodeError:
            payload = {"detail": raw[:300]}
        return exc.code, payload


@contextmanager
def _isolated_config_dir() -> Any:
    previous = os.environ.get("AGENT_LAB_CONFIG_DIR")
    with tempfile.TemporaryDirectory(prefix="dw-ft-soak-config-") as tmp:
        os.environ["AGENT_LAB_CONFIG_DIR"] = tmp
        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop("AGENT_LAB_CONFIG_DIR", None)
            else:
                os.environ["AGENT_LAB_CONFIG_DIR"] = previous


def _close_pending_after_journal(folder: Path, base_url: str, session_id: str) -> list[dict[str, Any]]:
    """Room may create clarifier inbox before journal; open gates then resolve via live API."""
    from agent_lab.human_inbox import pending_inbox_items
    from agent_lab.mission.dual_write import mirror_inbox_creation
    from agent_lab.run.meta import read_run_meta

    os.environ["AGENT_LAB_MISSION_DUAL_WRITE"] = "1"
    os.environ.pop("AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS", None)
    out: list[dict[str, Any]] = []
    for item in pending_inbox_items(read_run_meta(folder)):
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        mirror_inbox_creation(
            folder,
            item_id=item_id,
            kind=str(item.get("kind") or "question"),
            reason=str(item.get("summary") or item.get("prompt") or "soak-reconcile")[:200],
        )
        status, body = _http_json(
            "POST",
            f"{base_url.rstrip('/')}/api/sessions/{session_id}/inbox/{item_id}/resolve",
            {"decision": "feature", "note": "full-traffic soak auto-resolve"},
        )
        out.append(
            {
                "item_id": item_id,
                "status": status,
                "mirrored": (body.get("mission_dual_write") or {}).get("mirrored"),
            }
        )
    return out


def _one_turn(sessions_root: Path, topic: str, base_url: str) -> dict[str, Any]:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.run.meta import read_run_meta

    def _fake_peer_review(_folder: Path, *_args: object, **_kwargs: object) -> list[object]:
        return []

    def _fake_synthesize_plan(*_args: object, **_kwargs: object) -> str:
        return SAMPLE_PLAN

    def _noop_clarify(_folder: Path) -> None:
        return None

    with (
        patch("agent_lab.plan.workflow.run_plan_peer_review_round", _fake_peer_review),
        patch("agent_lab.room.synthesize_plan", _fake_synthesize_plan),
        patch("agent_lab.plan.workflow_clarify.ensure_plan_clarify_inbox_question", _noop_clarify),
        patch("agent_lab.plan.workflow_clarify.ensure_plan_clarify_interview", _noop_clarify),
    ):
        from agent_lab import room

        folder, messages, plan_md = room.run_room(
            topic,
            agents=["cursor", "codex", "claude"],
            synthesize=True,
            sessions_base=sessions_root,
            turn_profile="loop",
        )

    session_id = folder.name
    run = read_run_meta(folder)
    turns = run.get("turns") or []
    pw = (run.get("plan_workflow") or {}).get("phase")
    if pw not in {"HUMAN_PENDING", "APPROVED"}:
        set_plan_workflow_phase(folder, "HUMAN_PENDING")
    plan_path = folder / "plan.md"
    if not plan_path.is_file() or not plan_path.read_text(encoding="utf-8").strip():
        plan_path.write_text(plan_md or SAMPLE_PLAN, encoding="utf-8")

    status, body = _http_json(
        "POST",
        f"{base_url.rstrip('/')}/api/sessions/{session_id}/plan/approve",
        {"goal": topic},
    )
    bridge = body.get("mission_dual_write") or {}
    reconcile = _close_pending_after_journal(folder, base_url, session_id)
    return {
        "session_id": session_id,
        "topic": topic,
        "room_turns_recorded": len(turns),
        "agent_messages": sum(1 for m in messages if getattr(m, "role", None) not in ("human", None)),
        "approve_status": status,
        "mirrored": bridge.get("mirrored"),
        "enabled": bridge.get("enabled"),
        "reason": bridge.get("reason"),
        "inbox_reconcile": reconcile,
        "at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    import argparse
    import subprocess

    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, default=ROOT / "sessions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--turns", type=int, default=15)
    parser.add_argument("--prefix", default="dw-ft-soak")
    parser.add_argument("--artifact-dir", type=Path, default=Path("/tmp/agent-lab-dw-full-traffic-20260714"))
    args = parser.parse_args()

    args.sessions = args.sessions.resolve()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ.setdefault("AGENT_LAB_TURN_POLICY", "1")
    os.environ["AGENT_LAB_CLARIFIER"] = "0"
    os.environ["AGENT_LAB_PLAN_FSM_SKILL_FIRST"] = "0"
    os.environ.setdefault("AGENT_LAB_ROOM_PRESET", "supervisor")

    from agent_mocks import disable_execute_inbox_mcp
    import pytest

    monkeypatch = pytest.MonkeyPatch()
    disable_execute_inbox_mcp(monkeypatch)

    rows: list[dict[str, Any]] = []
    try:
        with _isolated_config_dir():
            for i in range(1, args.turns + 1):
                topic = f"{args.prefix} turn {i:02d}/{args.turns}: dual-write full-traffic soak"
                print(f"=== turn {i}/{args.turns} ===", flush=True)
                row = _one_turn(args.sessions, topic, args.base_url)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                if row.get("approve_status") != 200 or row.get("mirrored") is not True:
                    print("STOP: approve/mirror failed", flush=True)
                    break
    finally:
        monkeypatch.undo()

    allowlist = ",".join(r["session_id"] for r in rows)
    (args.artifact_dir / "soak-allowlist.txt").write_text(allowlist + "\n", encoding="utf-8")
    env = {**os.environ, "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS": allowlist}
    verify = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mission_dual_write_verify.py"), "--sessions", str(args.sessions), "--cohort"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    audit = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mission_dual_write_journal_audit.py"), "--sessions", str(args.sessions), "--cohort"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    verify_report = json.loads(verify.stdout) if verify.stdout.strip() else {"error": verify.stderr[:400]}
    audit_report = json.loads(audit.stdout) if audit.stdout.strip() else {"error": audit.stderr[:400]}

    health_status, health = _http_json("GET", f"{args.base_url.rstrip('/')}/api/health/daemon")
    report = {
        "kind": "full_traffic_soak",
        "target_turns": args.turns,
        "completed_turns": len(rows),
        "pass": (
            len(rows) >= args.turns
            and all(r.get("mirrored") is True and r.get("approve_status") == 200 for r in rows)
            and verify_report.get("hard_mismatch_count") == 0
            and audit_report.get("duplicate_count") == 0
        ),
        "turns": rows,
        "verify": {
            "hard_mismatch_count": verify_report.get("hard_mismatch_count"),
            "hard_mismatch_sessions": verify_report.get("hard_mismatch_sessions"),
        },
        "journal_audit": {"duplicate_count": audit_report.get("duplicate_count")},
        "health_status": health_status,
        "dual_write": health.get("dual_write"),
        "allowlist": allowlist,
        "ended_at": datetime.now(UTC).isoformat(),
    }
    out = args.artifact_dir / "reports" / "soak.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Human-readable ledger
    lines = [
        "# Dual-write Full traffic soak ledger — 2026-07-14",
        "",
        f"**승인:** Human 2026-07-14 · soak **≥{args.turns} Room turns** · legacy retire **금지**",
        f"**결과:** {'PASS' if report['pass'] else 'FAIL'} · completed {len(rows)}/{args.turns}",
        f"**verify hard_mm:** {report['verify']['hard_mismatch_count']} · **journal dup:** {report['journal_audit']['duplicate_count']}",
        "",
        "## Turn log",
        "",
        "| # | session_id | mirrored | hard | at |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for i, row in enumerate(rows, 1):
        lines.append(
            f"| {i} | `{row['session_id']}` | {row.get('mirrored')} | {row.get('approve_status')} | {row.get('at','')[:19]} |"
        )
    lines.extend(
        [
            "",
            "## Stop / PASS",
            "",
            f"- [{'x' if len(rows) >= args.turns else ' '}] {args.turns} turns 도달",
            f"- [{'x' if report['verify']['hard_mismatch_count'] == 0 else ' '}] hard_mm=0",
            f"- [{'x' if report['journal_audit']['duplicate_count'] == 0 else ' '}] duplicate=0",
            "- retire: **아직 승인하지 않음**",
            "",
        ]
    )
    (args.artifact_dir / "SOAK.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "completed_turns": len(rows), "verify": report["verify"], "journal_audit": report["journal_audit"]}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
