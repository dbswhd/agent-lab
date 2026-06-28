#!/usr/bin/env python3
"""Track 2.0 profile gate — measure repo_map + syntax_gate vs mock Room turn.

No LLM calls. Produces JSON + human summary for HYBRID-RUST-PYTHON-ADR gate N (default 5%).

Usage:
    .venv/bin/python scripts/profile_track2_gate.py
    .venv/bin/python scripts/profile_track2_gate.py --json
    make profile-track2-gate

Exit codes:
    0 — gate passed (Track 2 may proceed to 2.0b when platform gate also passes)
    2 — gate failed (Track 2 native POC closed; stay Python)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GATE_PCT = 5.0
DEFAULT_AGENT_STUB_MS = 30_000.0
DEFAULT_REPEAT = 3


@dataclass
class SegmentTiming:
    name: str
    ms: float
    repeat: int


@dataclass
class Track2ProfileReport:
    repo_root: str
    gate_threshold_pct: float
    agent_stub_ms: float
    segments: list[SegmentTiming] = field(default_factory=list)
    context_build_total_ms: float = 0.0
    repo_map_per_agent_ms: float = 0.0
    repo_tree_per_agent_ms: float = 0.0
    syntax_gate_ms: float = 0.0
    merge_checks_ms: float = 0.0
    native_candidates_ms: float = 0.0
    share_of_context_build_pct: float = 0.0
    share_of_mock_turn_pct: float = 0.0
    gate_passed: bool = False
    recommendation: str = ""
    notes: list[str] = field(default_factory=list)


def _best_ms(fn: Callable[[], Any], *, repeat: int = DEFAULT_REPEAT) -> tuple[Any, float]:
    best = float("inf")
    result: Any = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        best = min(best, (time.perf_counter() - t0) * 1000.0)
    return result, best


def _load_plan_md() -> str:
    candidates = [
        REPO_ROOT / "sessions/_regression/plan_workflow_pw5_latency/plan.md",
        REPO_ROOT / "sessions/_regression/discuss_challenge_resolved/plan.md",
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return "# plan\n\n- [ ] Touch `src/agent_lab/room/turn_flow.py`\n"


def _mock_run_meta(repo_root: Path) -> dict[str, Any]:
    return {
        "workspace_binding": {"path": str(repo_root)},
        "session_id": "profile-track2-gate",
        "room_preset": "supervisor",
        "context_layers": {
            "repo_tree": True,
            "wisdom_search": True,
        },
    }


def _mock_messages() -> list[Any]:
    from agent_lab.room.messages import ChatMessage

    return [
        ChatMessage(role="user", agent=None, content="Refactor room context bundle seams."),
        ChatMessage(
            role="agent",
            agent="codex",
            content="Break down `src/agent_lab/context/bundle.py` and tests.",
            parallel_round=1,
        ),
        ChatMessage(
            role="agent",
            agent="claude",
            content="Risk: gate_snapshot coupling. Add profile script first.",
            parallel_round=1,
        ),
    ]


def _realistic_pending_execution(repo_root: Path, *, max_files: int = 40) -> dict[str, Any]:
    paths: list[str] = []
    for path in sorted(repo_root.glob("src/agent_lab/**/*.py")):
        if path.is_file():
            paths.append(str(path.relative_to(repo_root)))
        if len(paths) >= max_files:
            break
    return {
        "isolation_effective": "worktree",
        "worktree_path": str(repo_root),
        "action_verify": "pytest -q",
        "source_touched_paths": paths,
        "touched_paths": paths[:20],
    }


def _tiny_fixture_root() -> Path:
    td = tempfile.mkdtemp(prefix="track2-profile-")
    root = Path(td)
    pkg = root / "src" / "app"
    pkg.mkdir(parents=True)
    for i in range(5):
        (pkg / f"mod_{i}.py").write_text(f"def fn_{i}():\n    return {i}\n", encoding="utf-8")
    (root / "plan.md").write_text("# plan\n\n- [ ] src/app/mod_0.py\n", encoding="utf-8")
    return root


def profile_repo(
    repo_root: Path,
    *,
    repeat: int = DEFAULT_REPEAT,
    agents: tuple[str, ...] = ("codex", "claude", "cursor"),
) -> Track2ProfileReport:
    from agent_lab.merge_checks import build_merge_checks
    from agent_lab.repo_map import build_repo_map_block
    from agent_lab.repo_tree_context import build_repo_tree_block
    from agent_lab.room.messages import build_agent_context_bundle
    from agent_lab.syntax_gate import evaluate_syntax_gate

    plan_md = _load_plan_md() if repo_root == REPO_ROOT else (repo_root / "plan.md").read_text()
    run_meta = _mock_run_meta(repo_root)
    messages = _mock_messages()
    pending = _realistic_pending_execution(repo_root)
    run_for_merge = {"pending_execution": pending, "merge": {}}

    segments: list[SegmentTiming] = []
    notes: list[str] = []

    os.environ["AGENT_LAB_REPO_MAP"] = "1"
    os.environ["AGENT_LAB_SYNTAX_GATE"] = "1"

    _, repo_map_ms = _best_ms(lambda: build_repo_map_block(run_meta, plan_md), repeat=repeat)
    segments.append(SegmentTiming("repo_map_block", repo_map_ms, repeat))

    os.environ.pop("AGENT_LAB_REPO_MAP", None)
    _, repo_tree_ms = _best_ms(lambda: build_repo_tree_block(run_meta), repeat=repeat)
    segments.append(SegmentTiming("repo_tree_block", repo_tree_ms, repeat))
    os.environ["AGENT_LAB_REPO_MAP"] = "1"

    context_ms_by_agent: dict[str, float] = {}
    for agent in agents:
        _, ms = _best_ms(
            lambda a=agent: build_agent_context_bundle(
                "Track 2 profile topic",
                messages,
                a,  # type: ignore[arg-type]
                plan_md=plan_md,
                run_meta=run_meta,
                parallel_round=1,
            ),
            repeat=repeat,
        )
        context_ms_by_agent[agent] = ms
        segments.append(SegmentTiming(f"context_bundle_{agent}", ms, repeat))

    context_total = sum(context_ms_by_agent.values())

    _, syntax_ms = _best_ms(lambda: evaluate_syntax_gate(pending), repeat=repeat)
    segments.append(SegmentTiming("syntax_gate", syntax_ms, repeat))

    _, merge_ms = _best_ms(lambda: build_merge_checks(run_for_merge, pending_execution=pending), repeat=repeat)
    segments.append(SegmentTiming("merge_checks", merge_ms, repeat))

    os.environ.pop("AGENT_LAB_REPO_MAP", None)
    os.environ.pop("AGENT_LAB_SYNTAX_GATE", None)

    native_ms = repo_map_ms * len(agents) + syntax_ms
    repo_map_turn_ms = repo_map_ms * len(agents)
    share_context = (repo_map_turn_ms / context_total * 100.0) if context_total else 0.0
    mock_turn_ms = context_total + syntax_ms + DEFAULT_AGENT_STUB_MS
    share_mock = (native_ms / mock_turn_ms * 100.0) if mock_turn_ms else 0.0

    gate_pct = DEFAULT_GATE_PCT
    gate_passed = share_context >= gate_pct or share_mock >= gate_pct

    # Typical production: AGENT_LAB_REPO_MAP default OFF — measure one agent for comparison.
    os.environ.pop("AGENT_LAB_REPO_MAP", None)
    _, context_tree_ms = _best_ms(
        lambda: build_agent_context_bundle(
            "Track 2 profile topic",
            messages,
            "codex",  # type: ignore[arg-type]
            plan_md=plan_md,
            run_meta=run_meta,
            parallel_round=1,
        ),
        repeat=repeat,
    )
    segments.append(SegmentTiming("context_bundle_codex_repo_tree", context_tree_ms, repeat))
    notes.append(
        f"REPO_MAP=1: repo_map ~{share_context:.1f}% of 3-agent context build; "
        f"REPO_MAP=0 codex bundle ~{context_tree_ms:.1f}ms (typical default-off path)"
    )
    if repo_root != REPO_ROOT:
        notes.append("tiny fixture root (tests only)")
    if repo_map_ms > repo_tree_ms * 10:
        notes.append(
            f"repo_map {repo_map_ms:.1f}ms vs repo_tree {repo_tree_ms:.1f}ms — flag-on context cost driver"
        )
    notes.append(
        f"mock turn uses {DEFAULT_AGENT_STUB_MS:.0f}ms agent stub (no real LLM/subprocess)"
    )

    if gate_passed:
        rec = (
            "Gate PASSED — profile shows native candidates meet threshold on at least one metric. "
            "Proceed to Track 2.0b (Python seam extract) when platform gate also passes."
        )
    else:
        rec = (
            "Gate FAILED — repo_map + syntax_gate are below gate threshold vs context/mock turn. "
            "Close Track 2 native POC; keep Python SSOT."
        )

    return Track2ProfileReport(
        repo_root=str(repo_root),
        gate_threshold_pct=gate_pct,
        agent_stub_ms=DEFAULT_AGENT_STUB_MS,
        segments=segments,
        context_build_total_ms=round(context_total, 3),
        repo_map_per_agent_ms=round(repo_map_ms, 3),
        repo_tree_per_agent_ms=round(repo_tree_ms, 3),
        syntax_gate_ms=round(syntax_ms, 3),
        merge_checks_ms=round(merge_ms, 3),
        native_candidates_ms=round(native_ms, 3),
        share_of_context_build_pct=round(share_context, 3),
        share_of_mock_turn_pct=round(share_mock, 3),
        gate_passed=gate_passed,
        recommendation=rec,
        notes=notes,
    )


def format_report(report: Track2ProfileReport) -> str:
    lines = [
        "Track 2.0 profile gate",
        f"  repo: {report.repo_root}",
        f"  gate threshold: {report.gate_threshold_pct}%",
        "",
        "Segments (best-of repeat ms):",
    ]
    for seg in report.segments:
        lines.append(f"  - {seg.name}: {seg.ms:.3f} ms (n={seg.repeat})")
    lines.extend(
        [
            "",
            f"  context_build_total: {report.context_build_total_ms:.3f} ms",
            f"  native_candidates (repo_map×3 + syntax_gate): {report.native_candidates_ms:.3f} ms",
            f"  repo_map share of context_build (REPO_MAP=1): {report.share_of_context_build_pct:.2f}%",
            f"  share_of_mock_turn (+{report.agent_stub_ms:.0f}ms stub): {report.share_of_mock_turn_pct:.2f}%",
            "",
            f"  GATE: {'PASS' if report.gate_passed else 'FAIL'}",
            f"  → {report.recommendation}",
        ]
    )
    for note in report.notes:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Track 2.0 profile gate")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument(
        "--fixture",
        choices=("repo", "tiny"),
        default="repo",
        help="Profile agent-lab repo (default) or tiny temp fixture",
    )
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--gate-pct", type=float, default=DEFAULT_GATE_PCT)
    parser.add_argument(
        "--write-baseline",
        type=Path,
        default=None,
        help="Write JSON report to path (e.g. tests/fixtures/track2-profile-report.json)",
    )
    args = parser.parse_args(argv)

    root = REPO_ROOT if args.fixture == "repo" else _tiny_fixture_root()
    report = profile_repo(root, repeat=max(1, args.repeat))
    report.gate_threshold_pct = args.gate_pct
    report.gate_passed = (
        report.share_of_context_build_pct >= args.gate_pct
        or report.share_of_mock_turn_pct >= args.gate_pct
    )
    if report.gate_passed:
        report.recommendation = (
            "Gate PASSED — profile shows native candidates meet threshold on at least one metric. "
            "Proceed to Track 2.0b (Python seam extract) when platform gate also passes."
        )
    else:
        report.recommendation = (
            "Gate FAILED — repo_map + syntax_gate are below gate threshold vs context/mock turn. "
            "Close Track 2 native POC; keep Python SSOT."
        )

    if args.write_baseline:
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.write_baseline.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report))

    return 0 if report.gate_passed else 2


if __name__ == "__main__":
    sys.exit(main())
