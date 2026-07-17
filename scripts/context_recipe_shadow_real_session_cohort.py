"""CX8 (09-context-engineering.md §11) — collect `context_recipe_shadow`
records from a REAL session cohort, not hand-authored synthetic run_meta.

`scripts/context_recipe_shadow_dogfood.py` (the first dogfood pass) used
one fully synthetic run_meta varied across a handful of dimensions. This
script instead drives `build_context_bundle` off:

1. **Checked-in regression fixtures** (`sessions/_regression/`,
   `docs/EXTERNAL-REFS-TRACEABILITY.md`'s golden baselines) — real
   `run.json` snapshots this repo already maintains as ground truth for
   specific mission-loop phases (`mission_loop_discuss_recovery`,
   `mission_loop_plan_reject`, `mission_loop_execute_queue`,
   `plan_workflow_pw5_latency`, `evidence_gates_merged_ok`,
   `evidence_ledger_stream`, `wisdom_index_built`). **Honesty about what's
   real here**: these fixtures ship ONLY `run.json` — no `chat.jsonl`,
   `plan.md`, or `workspace_binding` — because they're structural smoke-test
   baselines (`sessions/_regression/README.md`), not full session replays.
   `mission_loop`/`topic`/`executions` state is genuinely real; `plan_md`,
   `messages`, `workspace_binding`, and one representative `artifacts` entry
   are supplemented per scenario (documented per-record, not silently
   blended in).

2. **One freshly-driven real mock mission** (`build_real_repair_session`)
   — no existing regression fixture's `run.json` ends in `REPAIR` phase, so
   this drives an actual mission through the SAME real
   `mission/loop.py`/`mission/advance.py`/`verified_loop.py` functions
   `scripts/mission_dogfood_run.py` uses (not reimplemented/faked), except
   the Oracle verdict is forced to `fail` instead of `pass` to reach
   `REPAIR` instead of `MISSION_DONE`. `run.json`/`chat.jsonl`/`plan.md` are
   ALL genuinely real here — a session actually built on disk via real
   session-scratch functions, not supplemented after the fact. Written to a
   scratch directory (`--sessions`, defaults to a fresh temp dir) — NEVER
   `sessions/` in this repo (`sessions/*` is git-forbidden outside
   `sessions/_regression/`, per `CLAUDE.md`).

Still no coverage for CLARIFY (no regression fixture reaches it, and
driving a real clarifier interview flow is out of scope for this pass) or
SCRIBE (no mission phase maps to it at all — see
`context/bundle_recipe.py`'s own module docstring). Both gaps are reported,
not papered over.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
os.environ.setdefault("AGENT_LAB_MISSION_LOOP", "1")
os.environ["AGENT_LAB_CONTEXT_RECIPE"] = "1"

REGRESSION_ROOT = ROOT / "sessions" / "_regression"

REAL_FIXTURES: list[str] = [
    "mission_loop_discuss_recovery",
    "wisdom_index_built",
    "mission_loop_plan_reject",
    "mission_loop_execute_queue",
    "plan_workflow_pw5_latency",
    "evidence_gates_merged_ok",
    "evidence_ledger_stream",
]


@dataclass
class _Msg:
    role: str
    agent: str | None
    content: str
    parallel_round: int | None = None
    ts: str = ""


def _format_thread(topic: str, messages: list[_Msg]) -> str:
    lines = [f"Human topic:\n{topic}\n"]
    for m in messages:
        if m.role == "user":
            lines.append(f"Human:\n{m.content}\n")
        elif m.role == "agent" and m.agent:
            lines.append(f"{m.agent}:\n{m.content}\n")
    return "\n".join(lines)


_SUPPLEMENTED_PLAN = """# Plan (supplemented -- this fixture ships no plan.md)

## 지금 실행

1. Address the scenario this regression fixture represents
   - 무엇을: see the fixture's real `mission_loop`/`topic` state for what
     actually happened
   - 어디서: n/a (structural fixture, no real code change attached)
   - 검증: n/a
"""


def _supplemented_messages() -> list[_Msg]:
    return [
        _Msg("user", None, "(supplemented -- this fixture ships no chat.jsonl)", ts="2026-07-16T00:00:00Z"),
        _Msg("agent", "claude", "(supplemented reply for context-bundle assembly)", 1, ts="2026-07-16T00:00:01Z"),
    ]


def _load_real_fixture_run_meta(fixture_name: str) -> dict[str, Any]:
    path = REGRESSION_ROOT / fixture_name / "run.json"
    run_meta: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    # Supplemented fields -- these are structural fixtures with no
    # workspace_binding/plan_md/messages/artifacts of their own (see module
    # docstring). mission_loop/topic/executions above stay exactly as the
    # fixture ships them.
    run_meta.setdefault("workspace_binding", {"path": str(ROOT)})
    run_meta.setdefault(
        "artifacts",
        [
            {
                "id": "art-cohort-supplemented",
                "producer": "claude",
                "kind": "diff",
                "summary": f"(supplemented artifact for {fixture_name} -- fixture ships no room/artifacts.py data)",
                "ts": "2026-07-16T00:01:00Z",
            }
        ],
    )
    return run_meta


def run_fixture_scenario(fixture_name: str, *, agent: str = "claude") -> dict[str, Any]:
    from agent_lab.context.bundle import build_context_bundle

    run_meta = _load_real_fixture_run_meta(fixture_name)
    bundle = build_context_bundle(
        str(run_meta.get("topic") or fixture_name),
        _supplemented_messages(),
        agent,
        plan_md=_SUPPLEMENTED_PLAN,
        run_meta=run_meta,
        format_thread=_format_thread,
    )
    mission_loop = run_meta.get("mission_loop") or {}
    return {
        "scenario": f"fixture:{fixture_name}",
        "source": "real_fixture",
        "phase": mission_loop.get("phase"),
        "legacy_render_chars": len(bundle.render()),
        "slim_context": bundle.meta.slim_context,
        "shadow": run_meta.get("context_recipe_shadow"),
    }


_REPAIR_PLAN = """# Plan

## 지금 실행

1. Fix flaky retry logic
   - 무엇을: stabilize retry backoff in `src/retry.py`
   - 어디서: `src/retry.py`
   - 검증: `make test tests/test_retry.py` and `RETRY_OK` in `src/retry.py`
"""


def build_real_repair_session(sessions_root: Path, session_id: str) -> Path:
    """Drives one REAL mock mission through the actual mission_loop/
    verified_loop machinery (same functions scripts/mission_dogfood_run.py
    uses) to a genuine REPAIR phase -- forces the Oracle verdict to `fail`
    instead of `pass` at the verify step, since no existing regression
    fixture's run.json ends in REPAIR."""
    from agent_lab.mission.advance import on_verify_result
    from agent_lab.mission.loop import run_plan_gate
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.verified_loop import approve_verified_loop, init_verified_loop, record_proposed_goal

    folder = sessions_root / session_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text("stabilize retry backoff\n", encoding="utf-8")
    (folder / "plan.md").write_text(_REPAIR_PLAN, encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        json.dumps(
            {"role": "agent", "agent": "codex", "content": "Discuss: scope retry backoff fix."},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "stabilize retry backoff",
                "agents": ["cursor", "codex"],
                "status": "active",
                "turns": [{"mode": "discuss", "status": "completed"}],
                "actions": [],
                "approvals": [],
                "executions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    init_verified_loop(folder)
    record_proposed_goal(
        folder,
        {
            "goal": "Ship retry backoff fix",
            "completion_promise": "MISSION_DONE",
            "criteria": "tests pass",
        },
        source="real_session_cohort",
    )

    def _pending(run: dict[str, Any]) -> dict[str, Any]:
        run["verified_loop"]["status"] = "pending_approval"
        return run

    patch_run_meta(folder, _pending)
    approve_verified_loop(folder)

    gate = run_plan_gate(folder, _REPAIR_PLAN)
    if gate.get("status") != "ok":
        raise RuntimeError(f"plan gate failed: {gate}")

    def _verify_ready_then_fail(run: dict[str, Any]) -> dict[str, Any]:
        ml = run.setdefault("mission_loop", {})
        ml.update({"phase": "VERIFY", "last_execution_id": "exec-cohort-fail"})
        run["executions"] = [
            {
                "id": "exec-cohort-fail",
                "action_index": 1,
                "status": "merged",
                "isolation_effective": "worktree",
                "oracle": {
                    "verdict": "fail",
                    "detail": "RETRY_OK marker not found in src/retry.py",
                    "source": "mock",
                    "evidence": ["read 1 merged snippet(s)", "RETRY_OK marker missing"],
                },
            }
        ]
        return run

    patch_run_meta(folder, _verify_ready_then_fail)

    oracle = read_run_meta(folder)["executions"][0]["oracle"]
    on_verify_result(
        folder,
        action_index=1,
        verdict="fail",
        reason=str(oracle.get("detail") or ""),
        oracle=oracle,
    )

    phase = read_run_meta(folder)["mission_loop"]["phase"]
    if phase != "REPAIR":
        raise RuntimeError(f"expected REPAIR after forced Oracle fail, got {phase!r}")
    return folder


def _load_chat_jsonl(folder: Path) -> list[_Msg]:
    from agent_lab.session.chat_io import load_chat_dicts

    rows = load_chat_dicts(folder)
    return [
        _Msg(
            role=str(row.get("role") or ""),
            agent=row.get("agent"),
            content=str(row.get("content") or ""),
            parallel_round=row.get("parallel_round"),
            ts=str(row.get("ts") or ""),
        )
        for row in rows
    ]


def run_real_repair_scenario(sessions_root: Path, *, agent: str = "claude") -> dict[str, Any]:
    from agent_lab.context.bundle import build_context_bundle
    from agent_lab.run.meta import read_run_meta

    folder = build_real_repair_session(sessions_root, "context-recipe-cohort-repair")
    run_meta = read_run_meta(folder)
    run_meta.setdefault("workspace_binding", {"path": str(ROOT)})
    # REPAIR_RECIPE requires SourceClass.EVIDENCE (activity_recipes.py), but
    # room/artifacts.py's `artifacts` key is a Room per-turn producer the
    # mission_loop/verified_loop machinery this session was driven through
    # never touches -- everything else about this session (run.json,
    # chat.jsonl, plan.md, the REPAIR phase itself) is genuinely real, but
    # this one field is supplemented for the same reason the fixture-based
    # scenarios need it.
    run_meta.setdefault(
        "artifacts",
        [
            {
                "id": "art-cohort-repair-1",
                "producer": "claude",
                "kind": "diff",
                "summary": "(supplemented -- mission_loop/verified_loop don't populate room/artifacts.py's artifacts key)",
                "ts": "2026-07-16T00:01:00Z",
            }
        ],
    )
    plan_md = (folder / "plan.md").read_text(encoding="utf-8")
    topic = (folder / "topic.txt").read_text(encoding="utf-8").strip()
    messages = _load_chat_jsonl(folder)

    bundle = build_context_bundle(
        topic,
        messages,
        agent,
        plan_md=plan_md,
        run_meta=run_meta,
        format_thread=_format_thread,
    )
    return {
        "scenario": "real_repair_session",
        "source": "real_driven_mission",
        "phase": (run_meta.get("mission_loop") or {}).get("phase"),
        "legacy_render_chars": len(bundle.render()),
        "slim_context": bundle.meta.slim_context,
        "shadow": run_meta.get("context_recipe_shadow"),
    }


def run_cohort(sessions_root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = [run_fixture_scenario(name) for name in REAL_FIXTURES]
    records.append(run_real_repair_scenario(sessions_root))

    ok_records = [r for r in records if isinstance(r["shadow"], dict) and r["shadow"].get("ok")]
    skipped_records = [r for r in records if isinstance(r["shadow"], dict) and r["shadow"].get("skipped")]
    failed_records = [
        r
        for r in records
        if isinstance(r["shadow"], dict) and not r["shadow"].get("ok") and not r["shadow"].get("skipped")
    ]
    source_frequency: dict[str, int] = {}
    for r in ok_records:
        for source in r["shadow"].get("included_sources") or []:
            source_frequency[source] = source_frequency.get(source, 0) + 1

    return {
        "scenario_count": len(records),
        "ok_count": len(ok_records),
        "skipped_count": len(skipped_records),
        "failed_count": len(failed_records),
        "included_source_frequency": source_frequency,
        "per_scenario_ratio": {
            r["scenario"]: r["shadow"].get("recipe_to_legacy_token_ratio")
            for r in ok_records
        },
        "failed_scenarios": [
            {"scenario": r["scenario"], "error": r["shadow"].get("error")} for r in failed_records
        ],
        "not_covered": ["CLARIFY (no regression fixture reaches it)", "SCRIBE (no mission phase maps to it)"],
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sessions",
        type=Path,
        default=None,
        help="Scratch sessions dir for the freshly-driven REPAIR session (default: a fresh temp dir; NEVER this repo's sessions/)",
    )
    parser.add_argument("--out", type=Path, help="optional path to also write the JSON report to")
    parser.add_argument("--summary-only", action="store_true", help="omit the full per-scenario records list")
    args = parser.parse_args()

    sessions_root = args.sessions or Path(tempfile.mkdtemp(prefix="context-recipe-cohort-"))
    sessions_root.mkdir(parents=True, exist_ok=True)

    report = run_cohort(sessions_root)
    if args.summary_only:
        report = {k: v for k, v in report.items() if k != "records"}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(f"\n(scratch session dir: {sessions_root})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
