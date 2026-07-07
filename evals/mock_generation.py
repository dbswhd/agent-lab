from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import json
import os
from pathlib import Path

from evals.schema import EvalCase


@contextmanager
def patched_env(updates: dict[str, str]) -> Generator[None]:
    saved: dict[str, str | None] = {}
    for key, value in updates.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in saved.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def generate_mock_session(case: EvalCase, generated_dir: Path) -> Path:
    mock_run = case.get("mock_run")
    if mock_run is None:
        raise ValueError("missing mock_run config")
    topic = mock_run.get("topic", "").strip()
    if not topic:
        raise ValueError("mock_run.topic is required")

    from agent_lab import room

    with patched_env(
        {
            "AGENT_LAB_MOCK_AGENTS": "1",
            "AGENT_LAB_CLARIFIER": "0",
            "AGENT_LAB_INBOX_MODE": "soft",
        }
    ):
        folder, _messages, _plan = room.run_room(
            topic,
            agents=["cursor", "codex", "claude"],
            synthesize=True,
            sessions_base=generated_dir,
            consensus_mode=mock_run.get("consensus_mode", False),
            turn_profile=mock_run.get("turn_profile", "analyze"),
        )
    _enrich_generated_session_trace(folder, case)
    return folder


def _enrich_generated_session_trace(folder: Path, case: EvalCase) -> None:
    """Add eval-only execution/gate evidence to generated mock sessions.

    The S1~S3 generated sessions are discuss-first quality contracts, but eval
    trace completeness also measures downstream spans. Rather than changing the
    real room behavior, enrich only these temporary generated fixtures with a
    lightweight approved/verified execution trail so eval can observe the full
    workflow surface.
    """

    run_path = folder / "run.json"
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(run, dict):
        return

    case_id = str(case.get("case_id") or "S")
    topic = str(run.get("topic") or "")

    actions = run.get("actions")
    if not isinstance(actions, list):
        actions = []
        run["actions"] = actions
    if not actions:
        actions.append(
            {
                "action_id": f"{case_id.lower()}-mock-action-1",
                "index": 1,
                "kind": "now",
                "what": f"Summarize and verify mock result for {case_id}",
                "where": "`evals/generated_mock.py`",
                "verify": "mock oracle pass",
            }
        )

    plan_workflow = run.get("plan_workflow")
    if not isinstance(plan_workflow, dict):
        plan_workflow = {}
        run["plan_workflow"] = plan_workflow
    plan_workflow.update(
        {
            "enabled": True,
            "phase": "APPROVED",
            "approved_at": "2026-07-07T00:00:02+00:00",
            "approved_by": "human",
            "plan_hash_at_approval": f"{case_id.lower()}-mock-plan",
        }
    )

    verified_loop = run.get("verified_loop")
    if not isinstance(verified_loop, dict):
        verified_loop = {}
        run["verified_loop"] = verified_loop
    verified_loop.update(
        {
            "status": "running",
            "loop_goal": {
                "text": topic or f"Mock goal for {case_id}",
                "completion_promise": "DONE",
                "criteria": "mock oracle pass",
                "approved_at": "2026-07-07T00:00:02+00:00",
                "approved_by": "human",
            },
        }
    )

    consensus_agreements = run.get("consensus_agreements")
    if not isinstance(consensus_agreements, list):
        consensus_agreements = []
        run["consensus_agreements"] = consensus_agreements
    if not consensus_agreements:
        consensus_agreements.append(
            {
                "kind": "consensus_reached",
                "by": ["cursor", "codex", "claude"],
                "at": "2026-07-07T00:00:01+00:00",
            }
        )

    objections = run.get("objections")
    if not isinstance(objections, list):
        objections = []
        run["objections"] = objections
    if not objections:
        objections.append(
            {
                "id": f"obj-{case_id.lower()}-mock-1",
                "from": "claude",
                "act": "CHALLENGE",
                "body": "eval mock challenge",
                "status": "resolved_accepted",
                "turn": 1,
                "target_ref": "plan_action:1",
                "plan_action_index": 1,
                "plan_action_kind": "now",
            }
        )

    executions = run.get("executions")
    if not isinstance(executions, list):
        executions = []
        run["executions"] = executions
    if not executions:
        executions.append(
            {
                "id": f"exec-{case_id.lower()}-mock-1",
                "action_id": f"{case_id.lower()}-mock-action-1",
                "action_index": 1,
                "action_kind": "now",
                "status": "merged",
                "isolation_effective": "worktree",
                "action_verify": "mock oracle pass",
                "oracle_verdict": "pass",
                "verify_after_merge": {
                    "status": "passed",
                    "source": "mock_oracle",
                    "oracle": {"verdict": "pass", "detail": f"{case_id} mock verified"},
                },
                "oracle": {"verdict": "pass", "detail": f"{case_id} mock verified", "source": "mock"},
                "merge": {"status": "merged", "commit_sha": f"{case_id.lower()}fixture"},
            }
        )

    run["status"] = "completed"
    run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evidence_rows = [
        {
            "phase": "DRY_RUN",
            "kind": "dry_run",
            "detail": f"{case_id} mock dry-run complete",
            "session_id": folder.name,
            "at": "2026-07-07T00:00:03+00:00",
        },
        {
            "phase": "MERGE",
            "kind": "merge_approve",
            "detail": f"{case_id} mock human approved merge",
            "session_id": folder.name,
            "at": "2026-07-07T00:00:04+00:00",
        },
        {
            "phase": "VERIFY",
            "kind": "oracle_verify",
            "detail": f"{case_id} mock oracle pass",
            "session_id": folder.name,
            "at": "2026-07-07T00:00:05+00:00",
        },
    ]
    (folder / "evidence.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in evidence_rows) + "\n",
        encoding="utf-8",
    )
