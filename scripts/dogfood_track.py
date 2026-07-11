#!/usr/bin/env python3
"""Unified dogfood track — NOW.md closure criteria, **live-first**.

Default path is live supervisor dogfood (real agents, real ledger). Mock is
opt-in only (``--mode run-mock`` / ``make dogfood-track-run-mock``).

| ID | Closure | Live path (default) |
|----|---------|---------------------|
| P0-5 | history.n≥3 · explore>0 | supervisor Room + explore=0.1 |
| F7 | 7d ON/OFF | F7 flags ON → 7d use → Human decision |
| N4-D3 | escalation n≥10/level | autonomy-tagged live outcomes |
| CATALOG | suite-log coverage | live topics + ``dogfood-progress-record`` |
| HS-M5 | addressable + Human merge 1 | propose → Inbox approve |
| N1-30 | history.n≥30 | keep running live |

Modes:
  status / check — gate evaluation against live ledger
  env            — shell exports for ``make dev`` / ``make api``
  run            — **default live bootstrap**: env reminder, F7 start, next actions
  run-mock       — optional mock arms (CI / offline only)
  record-f7-decision / record-hs-m5-merge / mark-f7-start

Does **not** bypass Human gates.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for _p in (ROOT / "src", SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

STATE_PATH = ROOT / ".agent-lab" / "dogfood-track.json"
DEFAULT_LOG = ROOT / "sessions" / "_benchmark" / "topics" / "suite-log.json"
DEFAULT_TOPICS = ROOT / "sessions" / "_benchmark" / "topics" / "dogfood-v1.json"
REPORTS = ROOT / "sessions" / "_reports"

# Closure thresholds (SSOT pointers — do not invent new IDs)
P05_HISTORY_N = 3
P05_EXPLORE_MIN = 1
N4_PER_LEVEL_N = 10
N1_HISTORY_N = 30
F7_MIN_SESSIONS = 10
F7_COVERAGE_PCT = 70.0
CATALOG_MANUAL_IDS = ("L4", "A1")  # live-only catalog leftovers after X3/X4 mock arms


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"schema": 1, "f7": {}, "hs_m5": {}, "notes": []}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "f7": {}, "hs_m5": {}, "notes": []}
    return data if isinstance(data, dict) else {"schema": 1}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _feedback_report(root: Path | None = None) -> dict[str, Any]:
    from agent_lab.feedback_report import build_feedback_report

    return build_feedback_report(root)


def _level_sample_counts(rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Count outcome rows per autonomy_level (N4 D3 sample gate)."""
    if rows is None:
        from agent_lab.feedback_report import _load_rows

        rows = _load_rows(None)
    counts = {"L0": 0, "L1": 0, "L2": 0, "L3": 0}
    for row in rows or []:
        if str(row.get("phase") or "") == "user_correction":
            continue
        level = str(row.get("autonomy_level") or "L0")
        if level not in counts:
            level = "L0"
        counts[level] += 1
    return counts


def _f7_report(*, days: int = 7) -> dict[str, Any]:
    mod = _load_module("f7_dogfood_report", SCRIPTS / "f7_dogfood_report.py")
    rows = mod.collect_sessions(ROOT / "sessions", days=days)
    return mod.build_report(rows)


def _addressable() -> list[dict[str, Any]]:
    from agent_lab.harness_proposer import addressable_patterns, ensure_manifest

    ensure_manifest(None)
    return addressable_patterns(root=None)


def _harness_patch_merged(state: dict[str, Any]) -> bool:
    """HS-M5 live close: Human-recorded merge OR merge_gate stats show ≥1 merge."""
    if state.get("hs_m5", {}).get("merged_at"):
        return True
    try:
        from agent_lab.merge_gate import harness_patch_stats

        stats = harness_patch_stats(None)
        return int(stats.get("candidates_merged") or 0) >= 1
    except Exception:  # noqa: BLE001
        return False


def evaluate_gates(*, outcomes_root: Path | None = None) -> dict[str, Any]:
    """Evaluate every track gate. ``met`` = closure satisfied."""
    state = _load_state()
    fb = _feedback_report(outcomes_root)
    by_source = fb.get("by_source") or {}
    history_n = int((by_source.get("history") or {}).get("n") or 0)
    explore_turn = int((fb.get("turn_source_counts") or {}).get("explore") or 0)
    explore_exec_n = int((by_source.get("explore") or {}).get("n") or 0)
    explore_n = max(explore_turn, explore_exec_n)
    lift = (fb.get("advisor_lift") or {}).get("history_vs_default")

    level_counts = _level_sample_counts()
    n4_ok = all(level_counts[lv] >= N4_PER_LEVEL_N for lv in ("L0", "L1", "L2", "L3"))

    f7 = _f7_report(days=7)
    f7_decision = str((state.get("f7") or {}).get("decision") or "").upper()
    f7_decided = f7_decision in {"ON", "OFF"}

    progress_mod = _load_module("dogfood_progress", SCRIPTS / "dogfood_progress.py")
    suite = progress_mod._load_suite()
    topics = suite.load_topics(DEFAULT_TOPICS)
    log_rows = progress_mod._load_json_list(DEFAULT_LOG)
    progress = progress_mod.build_progress(topics, log_rows)
    # Catalog "met" when all automatable topics done AND manual leftovers recorded or waived
    catalog_auto_done = progress["remaining_auto"] == 0
    manual_left = set(progress["remaining_manual_ids"])
    catalog_manual_ok = manual_left <= set(CATALOG_MANUAL_IDS) or len(manual_left) == 0
    # Still require X3/X4 in done if they are automatable now
    catalog_met = catalog_auto_done and (not manual_left or manual_left <= set(CATALOG_MANUAL_IDS))

    patterns = _addressable()
    hs_merged = _harness_patch_merged(state)
    hs_m5_met = bool(patterns) and hs_merged

    gates: list[dict[str, Any]] = [
        {
            "id": "P0-5",
            "title": "S1 lift + explore (live close)",
            "source": "WORKFLOW P0-5 · NORTH-STAR N1",
            "met": history_n >= P05_HISTORY_N and explore_n >= P05_EXPLORE_MIN,
            "metrics": {
                "history_n": history_n,
                "explore_n": explore_n,
                "advisor_lift.history_vs_default": lift,
                "need": f"history.n≥{P05_HISTORY_N} · explore≥{P05_EXPLORE_MIN}",
            },
            "live_cmd": 'eval "$(make -s dogfood-track-env)" && make dev  # supervisor · Plan OFF for S1 · explore on',
            "optional_mock": "make dogfood-feedback-mock REPEAT=4",
        },
        {
            "id": "F7",
            "title": "repo_map/compaction 7d ON/OFF",
            "source": "NORTH-STAR F7",
            "met": bool(f7.get("ready_for_decision")) and f7_decided,
            "metrics": {
                "ready_for_decision": f7.get("ready_for_decision"),
                "gates": f7.get("gates"),
                "sessions": f7.get("f7_instrumented_sessions"),
                "coverage_pct": f7.get("repo_map_coverage_pct"),
                "decision": f7_decision or None,
                "need": f"≥{F7_MIN_SESSIONS} instrumented · coverage≥{F7_COVERAGE_PCT}% · Human ON/OFF",
            },
            "live_cmd": "make dogfood-track-f7-start → use 7d → make f7-dogfood-report → make dogfood-track-f7-decision DECISION=ON|OFF",
            "optional_mock": "make f7-dogfood-report JSON=1  # read-only instrumentation",
        },
        {
            "id": "N4-D3",
            "title": "escalation_rate_by_level n≥10/level",
            "source": "NORTH-STAR §1.4.1",
            "met": n4_ok,
            "metrics": {
                "level_counts": level_counts,
                "escalation_rate_by_level": fb.get("escalation_rate_by_level"),
                "need": f"each L0–L3 ≥{N4_PER_LEVEL_N} tagged outcome rows",
            },
            "live_cmd": "supervisor dogfood across L0–L3 ceilings; make feedback-report JSON=1",
            "optional_mock": None,
        },
        {
            "id": "CATALOG",
            "title": "dogfood-v1 suite coverage",
            "source": "EVAL-PROGRAM · dogfood_progress",
            "met": catalog_met,
            "metrics": {
                "done": progress["done"],
                "total": progress["total"],
                "pct_done": progress["pct_done"],
                "remaining_auto": progress["remaining_auto_ids"],
                "remaining_manual": progress["remaining_manual_ids"],
                "manual_expected": list(CATALOG_MANUAL_IDS),
                "catalog_manual_ok": catalog_manual_ok,
            },
            "live_cmd": "make dogfood-suite-checklist · live Room · make dogfood-progress-record ID=… SESSION=sessions/…",
            "optional_mock": "make dogfood-progress-auto  # offline catalog only",
        },
        {
            "id": "HS-M5",
            "title": "addressable pattern + Human harness_patch merge ≥1",
            "source": "HSIL · NOW §1",
            "met": hs_m5_met,
            "metrics": {
                "addressable_count": len(patterns),
                "addressable_ids": [p.get("pattern_id") for p in patterns[:8]],
                "merged": hs_merged,
                "need": "addressable≥1 AND live Human merge of harness_patch",
            },
            "live_cmd": "python scripts/propose_harness.py --mode list → propose → Inbox approve → make dogfood-track-hs-m5-merge",
            "optional_mock": None,
        },
        {
            "id": "N1-30",
            "title": "dogfood-first expiry review (history.n≥30)",
            "source": "NORTH-STAR §3.3 branch",
            "met": history_n >= N1_HISTORY_N,
            "metrics": {
                "history_n": history_n,
                "need": f"history.n≥{N1_HISTORY_N}",
            },
            "live_cmd": "continue supervisor dogfood; make feedback-report JSON=1",
            "optional_mock": None,
        },
    ]

    met_n = sum(1 for g in gates if g["met"])
    return {
        "generated_at": _utc_now(),
        "met": met_n,
        "total": len(gates),
        "all_met": met_n == len(gates),
        "gates": gates,
        "feedback_snapshot": {
            "total": fb.get("total"),
            "verdict_eligible_total": fb.get("verdict_eligible_total"),
            "turn_source_counts": fb.get("turn_source_counts"),
            "by_source_n": {k: (v or {}).get("n") for k, v in by_source.items()},
            "advisor_lift": fb.get("advisor_lift"),
        },
        "state_path": str(STATE_PATH),
    }


def render_status(report: dict[str, Any]) -> str:
    lines = [
        f"Dogfood track (live-first) — {report['met']}/{report['total']} gates closed",
        "",
    ]
    for g in report["gates"]:
        mark = "✓" if g["met"] else "·"
        lines.append(f"  {mark} [{g['id']}] {g['title']}")
        need = (g.get("metrics") or {}).get("need")
        if need and not g["met"]:
            lines.append(f"      need: {need}")
        if not g["met"]:
            lines.append(f"      next: {g.get('live_cmd')}")
    lines.append("")
    snap = report.get("feedback_snapshot") or {}
    lines.append(
        f"ledger: total={snap.get('total')} eligible={snap.get('verdict_eligible_total')} "
        f"sources={snap.get('by_source_n')}"
    )
    if report.get("all_met"):
        lines.append("ALL GATES MET — dogfood track complete for NOW backlog.")
    else:
        lines.append('Next: eval "$(make -s dogfood-track-env)" && make dev  # then re-check with make dogfood-track')
    return "\n".join(lines)


def print_live_env() -> int:
    """Exports for API process — S1 + explore + F7 + execute lift."""
    lines = [
        "# Dogfood track LIVE env — eval before `make dev` / `make api`",
        "# UI: preset supervisor · Plan OFF for S1 discuss · Plan ON for X2 execute",
        "export AGENT_LAB_TURN_METRICS=1",
        "export AGENT_LAB_OUTCOME_LEDGER=1",
        "export AGENT_LAB_FEEDBACK_ADVISOR=1",
        "export AGENT_LAB_FEEDBACK_EXPLORE_RATE=0.1",
        "export AGENT_LAB_REPO_MAP=1",
        "export AGENT_LAB_COMPACT_TOOL_OUTPUT=1",
        "export AGENT_LAB_EXECUTE_INBOX=0",
        "unset AGENT_LAB_MOCK_AGENTS 2>/dev/null || true",
        "unset AGENT_LAB_OUTCOMES_ROOT 2>/dev/null || true",
        "unset AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES 2>/dev/null || true",
        "# Mid-turn gates (Question / build / plan / execute):",
        "#   make dogfood-live-gates-watch SESSION_ID=<id>",
    ]
    print("\n".join(lines))
    return 0


def run_live(*, skip_f7_start: bool = False) -> int:
    """Live bootstrap: pin F7 start, print env + next actions for unmet gates."""
    if not skip_f7_start:
        mark_f7_start()

    print("\n=== LIVE env (eval this, then make dev / make api) ===\n")
    print_live_env()

    report = evaluate_gates()
    print("\n=== gate status ===")
    print(render_status(report))

    open_gates = [g for g in report["gates"] if not g["met"]]
    if open_gates:
        print("\n=== next live actions ===")
        for g in open_gates:
            print(f"  [{g['id']}] {g.get('live_cmd')}")
        print("\nAfter sessions:")
        print("  make dogfood-track")
        print("  make feedback-report JSON=1")
        print("  make f7-dogfood-report JSON=1")
        print("  make dogfood-progress-record ID=<topic> SESSION=sessions/<id>")
        print("  make dogfood-live-gates-watch SESSION_ID=<id>  # Question/MCP/execute mid-gates")

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPORTS / f"dogfood-track-live-{stamp}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"\nreport: {out}")
    return 0 if report.get("all_met") else 0  # bootstrap always 0; use --mode check to gate CI


def run_mock_early(*, only: set[str] | None = None) -> int:
    """Optional mock arms (offline/CI). Not the default dogfood path."""
    print("NOTE: mock path is optional — default dogfood track is LIVE.\n")
    rc = 0
    want = only or {"P0-5", "CATALOG", "HS-M5", "F7"}

    if "P0-5" in want:
        print("\n=== P0-5 optional mock: dogfood-feedback-mock ===")
        env = os.environ.copy()
        env["AGENT_LAB_MOCK_AGENTS"] = "1"
        env["AGENT_LAB_FEEDBACK_EXPLORE_RATE"] = env.get("AGENT_LAB_FEEDBACK_EXPLORE_RATE") or "0.1"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "run_dogfood_suite.py"),
                "--mode",
                "mock",
                "--feedback",
                "--repeat",
                "4",
                "--tier",
                "S",
            ],
            cwd=ROOT,
            env=env,
            check=False,
        )
        rc |= proc.returncode

    if "CATALOG" in want:
        print("\n=== CATALOG optional mock: dogfood-progress-auto ===")
        progress = _load_module("dogfood_progress", SCRIPTS / "dogfood_progress.py")
        suite = progress._load_suite()
        topics = suite.load_topics(DEFAULT_TOPICS)
        rc |= progress.run_auto(
            topics,
            log_path=DEFAULT_LOG,
            sessions_base=Path(tempfile.mkdtemp(prefix="dogfood-track-")),
            only=None,
            skip_done=True,
            dry_run=False,
        )

    if "HS-M5" in want:
        print("\n=== HS-M5: propose_harness --mode list ===")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "propose_harness.py"), "--mode", "list"],
            cwd=ROOT,
            check=False,
        )
        rc |= proc.returncode

    if "F7" in want:
        print("\n=== F7: f7-dogfood-report (read-only) ===")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "f7_dogfood_report.py"), "--sessions", "sessions", "--days", "7"],
            cwd=ROOT,
            check=False,
        )
        rc |= proc.returncode

    print("\n=== post-run gate status ===")
    report = evaluate_gates()
    print(render_status(report))
    return rc


def mark_f7_start() -> int:
    state = _load_state()
    f7 = state.setdefault("f7", {})
    if not f7.get("start_date"):
        f7["start_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print(f"F7 start_date set to {f7['start_date']}")
    else:
        print(f"F7 start_date already {f7['start_date']}")
    _save_state(state)
    return 0


def record_f7_decision(decision: str, *, rationale: str = "") -> int:
    decision = decision.upper().strip()
    if decision not in {"ON", "OFF"}:
        print("decision must be ON or OFF", file=sys.stderr)
        return 2
    state = _load_state()
    f7 = state.setdefault("f7", {})
    f7["decision"] = decision
    f7["decided_at"] = _utc_now()
    f7["rationale"] = rationale
    f7["end_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _save_state(state)
    print(f"F7 decision recorded: {decision}")
    print("Also update docs/F7-REPO-MAP-COMPACTION-DOGFOOD.md Decision table.")
    return 0


def record_hs_m5_merge(*, candidate_id: str = "", notes: str = "") -> int:
    state = _load_state()
    hs = state.setdefault("hs_m5", {})
    hs["merged_at"] = _utc_now()
    hs["candidate_id"] = candidate_id
    hs["notes"] = notes
    _save_state(state)
    print("HS-M5 Human merge recorded in dogfood-track state.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--mode",
        choices=[
            "status",
            "check",
            "env",
            "run",
            "run-mock",
            "mark-f7-start",
            "record-f7-decision",
            "record-hs-m5-merge",
        ],
        default="status",
        help="default status; use 'run' for live bootstrap (not run-mock)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--only", help="run-mock only: comma gate ids (P0-5,CATALOG,HS-M5,F7)")
    parser.add_argument("--decision", help="record-f7-decision: ON|OFF")
    parser.add_argument("--rationale", default="")
    parser.add_argument("--candidate-id", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--outcomes-root", type=Path, default=None)
    parser.add_argument("--skip-f7-start", action="store_true", help="run: do not pin F7 start_date")
    args = parser.parse_args()

    if args.mode == "env":
        return print_live_env()
    if args.mode == "run":
        return run_live(skip_f7_start=args.skip_f7_start)
    if args.mode == "mark-f7-start":
        return mark_f7_start()
    if args.mode == "record-f7-decision":
        if not args.decision:
            print("--decision ON|OFF required", file=sys.stderr)
            return 2
        return record_f7_decision(args.decision, rationale=args.rationale)
    if args.mode == "record-hs-m5-merge":
        return record_hs_m5_merge(candidate_id=args.candidate_id, notes=args.notes)
    if args.mode == "run-mock":
        only = {x.strip().upper() for x in args.only.split(",")} if args.only else None
        return run_mock_early(only=only)

    report = evaluate_gates(outcomes_root=args.outcomes_root)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print(render_status(report))
    if args.mode == "check":
        return 0 if report["all_met"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
