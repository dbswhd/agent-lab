"""HS4 REGRESS — decision-theoretic regression gate for PatchCandidate.

Flag-gated (``AGENT_LAB_REGRESSION_GATE``, default off). See
docs/DESIGN-HARNESS-SELF-IMPROVE.md §8.4, §9 HS4.

**Gate principle (REVIEW P0-1 — "분류기는 신호, 검증기가 게이트"):** held-in/held-out
pass rates are candidate-ranking *signal* only. The merge ``verdict`` is decided
by (a) HS4-1's declared assertions running green in an isolated worktree and
(b) the structural checks (files match the diff, no Tier C touch, no
resolved-pattern regression, eval surface accounted for) — never by a bare
pass-rate threshold.

Isolation note: a git worktree shares this checkout's ``.venv``, so pytest run
against the worktree's files would otherwise still import the *main*
checkout's ``agent_lab`` package (editable install resolves by package name,
not cwd) — silently testing the wrong code. ``_pytest_env`` fixes this by
prepending the worktree's ``src/`` to ``PYTHONPATH``, verified to correctly
shadow the main checkout (see HS4 implementation notes in the design doc).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_lab.time_utils import utc_now_iso_seconds as _now_iso
from agent_lab.env_flags import env_bool

REGRESSION_REPORT_SCHEMA_VERSION = 1

# HS4-2 held-in — primary_tag -> dogfood topic ids known to exercise it.
# Every tag maps to a concretely-evidenced scenario (scripts/run_dogfood_suite.py):
# weak_taste -> M3/M4 script a BLOCK/CHALLENGE; harness_infra -> X5 asserts
# oracle_verify() returns "skipped" for a bare (no 검증:) action; false_success
# -> X6 asserts oracle_verify() returns pass with no evidence via a scripted
# oracle_call. Each matches turn_metrics.derive_execution_failure_tags's exact
# detection trigger (2026-07-09, HS4-2 completion — see docs/DESIGN-HARNESS-SELF-IMPROVE.md).
_TAG_TOPIC_MAP: dict[str, list[str]] = {
    "weak_taste": ["M3", "M4"],
    "harness_infra": ["X5"],
    "false_success": ["X6"],
}


def regression_gate_enabled() -> bool:
    """AGENT_LAB_REGRESSION_GATE (default off)."""
    return env_bool("AGENT_LAB_REGRESSION_GATE")


class RegressionRejected(Exception):
    """A candidate failed a structural (pre-execution) regression check."""


# ---------------------------------------------------------------------------
# HS4-2 — resolved_patterns.jsonl (append-only cumulative held-in set)
# ---------------------------------------------------------------------------


def resolved_patterns_path(root: Path | None = None) -> Path:
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "harness" / "resolved_patterns.jsonl"


def load_resolved_patterns(root: Path | None = None) -> list[dict[str, Any]]:
    path = resolved_patterns_path(root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("pattern_id"):
            rows.append(row)
    return rows


def record_resolved_pattern(pattern_id: str, *, candidate_id: str, root: Path | None = None) -> None:
    """Append-only — called by HS5 on successful merge. Never rewrites a row."""
    path = resolved_patterns_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"pattern_id": pattern_id, "candidate_id": candidate_id, "resolved_at": _now_iso()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _primary_tag_of(pattern_id: str) -> str | None:
    # pattern_id = "fp:{primary_tag}:{category}" (weakness_miner.mine_weakness_patterns)
    parts = pattern_id.split(":")
    return parts[1] if len(parts) >= 2 else None


def held_in_topics_for_tag(primary_tag: str) -> list[str]:
    return list(_TAG_TOPIC_MAP.get(primary_tag, []))


def held_in_scope(candidate: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """HS4-2 — this candidate's own tag topics + every already-resolved pattern's
    tag topics (REVIEW P0-2 cumulative set — prevents reintroducing a fixed pattern)."""
    own_tag = _primary_tag_of(str(candidate.get("pattern_id") or ""))
    topics: set[str] = set(held_in_topics_for_tag(own_tag)) if own_tag else set()
    source_patterns = [str(candidate.get("pattern_id") or "")] if own_tag else []

    for row in load_resolved_patterns(root):
        tag = _primary_tag_of(str(row.get("pattern_id") or ""))
        if not tag:
            continue
        resolved_topics = held_in_topics_for_tag(tag)
        if resolved_topics:
            topics.update(resolved_topics)
            source_patterns.append(str(row.get("pattern_id")))

    return {"topics": sorted(topics), "source_patterns": source_patterns}


# ---------------------------------------------------------------------------
# diff introspection (defense in depth — don't just trust candidate.files)
# ---------------------------------------------------------------------------

_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_FLAG_RE = re.compile(r"AGENT_LAB_[A-Z0-9_]+")


def parse_diff_touched_files(diff_text: str) -> list[str]:
    """Repo-relative paths from unified-diff ``+++ b/...`` headers, deduped, sorted."""
    return sorted(set(_DIFF_FILE_RE.findall(diff_text)))


def diff_introduces_new_flags(diff_text: str) -> set[str]:
    """AGENT_LAB_* tokens in the diff's added lines that aren't already registered (F10)."""
    added_lines = [line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]
    tokens = set(_FLAG_RE.findall("\n".join(added_lines)))
    if not tokens:
        return set()
    from agent_lab.runtime_flags import FLAG_REGISTRY

    known = {f.name for f in FLAG_REGISTRY}
    return tokens - known


def diff_touches_manifest(diff_text: str) -> bool:
    return ".agent-lab/harness/manifest.json" in parse_diff_touched_files(diff_text)


def eval_surface_gate_reason(candidate: dict[str, Any], diff_text: str) -> str | None:
    """HS4-6 — independent re-check of HS3-6 (defense in depth: the proposer's own
    ``introduces_new_surface`` flag is caller-declared and could be omitted).
    None means the gate passes."""
    if candidate.get("eval_additions"):
        return None
    new_flags = diff_introduces_new_flags(diff_text)
    if new_flags:
        return f"diff introduces unregistered flag(s) {sorted(new_flags)} without eval_additions"
    if diff_touches_manifest(diff_text):
        return "diff touches manifest.json (new editable surface) without eval_additions"
    return None


# ---------------------------------------------------------------------------
# worktree mechanics (plain git — no Room/session coupling, no Tier C touch)
# ---------------------------------------------------------------------------


def _run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)


def create_regression_worktree(git_root: Path, *, label: str) -> Path:
    """``git worktree add`` a detached checkout of HEAD under a temp dir."""
    import tempfile

    wt_path = Path(tempfile.mkdtemp(prefix=f"regress-{label}-"))
    _run_git(git_root, "worktree", "add", "--detach", str(wt_path), "HEAD")
    return wt_path


def remove_regression_worktree(git_root: Path, worktree: Path) -> None:
    """Best-effort cleanup — never raises."""
    try:
        _run_git(git_root, "worktree", "remove", "--force", str(worktree), check=False)
    except OSError:
        pass
    import shutil

    shutil.rmtree(worktree, ignore_errors=True)


def apply_diff(worktree: Path, diff_path: Path) -> tuple[bool, str]:
    """``git apply --check`` then apply. Returns (ok, stderr)."""
    if not diff_path.is_file() or not diff_path.read_text(encoding="utf-8").strip():
        return False, f"diff file missing or empty: {diff_path}"
    check = _run_git(worktree, "apply", "--check", str(diff_path), check=False)
    if check.returncode != 0:
        return False, check.stderr
    applied = _run_git(worktree, "apply", str(diff_path), check=False)
    return applied.returncode == 0, applied.stderr


def _pytest_env(worktree: Path) -> dict[str, str]:
    """PYTHONPATH override so pytest imports the worktree's copy, not the main
    checkout's editable-installed package (see module docstring)."""
    env = dict(os.environ)
    src = str(worktree / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
    env["AGENT_LAB_MOCK_AGENTS"] = "1"
    return env


# ---------------------------------------------------------------------------
# HS4-1 — declared assertions (the actual merge gate, per REVIEW P0-1)
# ---------------------------------------------------------------------------


@dataclass
class AssertionResult:
    node_id: str
    passed: bool
    detail: str


def _run_pytest(node_ids: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Thin, monkeypatchable subprocess wrapper — tests patch this directly
    rather than injecting a runner callable (matches this codebase's existing
    monkeypatch-module-function convention)."""
    import sys

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *node_ids],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def run_assertions(worktree: Path, assertions: list[str]) -> list[AssertionResult]:
    """HS4-1 — run each declared pytest node id individually so one failure
    doesn't obscure which specific assertion regressed."""
    results = []
    env = _pytest_env(worktree)
    for node_id in assertions:
        proc = _run_pytest([node_id], cwd=worktree, env=env)
        results.append(AssertionResult(node_id=node_id, passed=proc.returncode == 0, detail=proc.stdout[-2000:]))
    return results


# ---------------------------------------------------------------------------
# HS4-3 — held-out (test-fast minus held-in)
# ---------------------------------------------------------------------------


def run_held_out(worktree: Path, *, exclude_topics: list[str]) -> dict[str, Any]:
    """test-fast in the worktree. ``exclude_topics`` documents the held-in
    scope in the report (dogfood topics aren't pytest node ids, so the actual
    exclusion is enforced by held_in_scope() at candidate-selection time, not
    by filtering this pytest run — see HS4-2)."""
    env = _pytest_env(worktree)
    proc = _run_pytest(["tests/", "-m", "not live and not integration and not bridge"], cwd=worktree, env=env)
    return {
        "scope": "test-fast minus held_in",
        "excluded_topics": list(exclude_topics),
        "pass": proc.returncode == 0,
        "detail": proc.stdout[-2000:] if proc.returncode != 0 else "",
    }


# ---------------------------------------------------------------------------
# HS4-4 — smoke signal (Mission REPAIR verify signal = smoke, scoped to 1 pass)
# ---------------------------------------------------------------------------


def run_smoke_signal(worktree: Path) -> dict[str, Any]:
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/smoke_room.py"],
        cwd=worktree,
        capture_output=True,
        text=True,
        env=_pytest_env(worktree),
    )
    return {"pass": proc.returncode == 0, "detail": proc.stdout[-1000:] if proc.returncode != 0 else ""}


# ---------------------------------------------------------------------------
# RegressionGateReport (§8.4) + orchestrator
# ---------------------------------------------------------------------------


@dataclass
class RegressionGateReport:
    candidate_id: str
    held_in: dict[str, Any]
    held_out: dict[str, Any]
    smoke: dict[str, Any]
    resolved_patterns_checked: list[str]
    eval_surface_expanded: bool
    assertions: list[dict[str, Any]]
    verdict: str
    reason: str
    generated_at: str


def _report_path(candidate_id: str, *, root: Path | None = None) -> Path:
    from agent_lab.harness_proposer import candidates_root

    return candidates_root(root) / candidate_id / "regression_report.json"


def write_report(report: RegressionGateReport, *, root: Path | None = None) -> Path:
    """HS4-5 — always written, pass or fail (negative results preserved)."""
    path = _report_path(report.candidate_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"v": REGRESSION_REPORT_SCHEMA_VERSION, **asdict(report)}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_report(candidate_id: str, *, root: Path | None = None) -> dict[str, Any] | None:
    """HS5 MERGE consumer — None when no report has been written yet."""
    path = _report_path(candidate_id, root=root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def run_regression_gate(
    candidate_id: str,
    *,
    diff_path: Path,
    git_root: Path,
    root: Path | None = None,
) -> RegressionGateReport:
    """Orchestrates HS4-1..HS4-6 for one candidate. Always writes a report
    (HS4-5), including on structural rejection before a worktree is even
    created."""
    from agent_lab.harness_proposer import load_candidate

    candidate = load_candidate(candidate_id, root=root)
    assertions_declared = list(candidate.get("assertions") or [])

    def _reject(reason: str) -> RegressionGateReport:
        report = RegressionGateReport(
            candidate_id=candidate_id,
            held_in={},
            held_out={},
            smoke={},
            resolved_patterns_checked=[],
            eval_surface_expanded=False,
            assertions=[],
            verdict="fail",
            reason=reason,
            generated_at=_now_iso(),
        )
        write_report(report, root=root)
        return report

    # HS4-1: assertions must be declared — the actual deterministic gate.
    if not assertions_declared:
        return _reject("HS4-1: candidate declares no assertions (REVIEW P0-1 requires a deterministic gate)")

    if not diff_path.is_file():
        return _reject(f"diff file not found: {diff_path}")
    diff_text = diff_path.read_text(encoding="utf-8")

    # Defense in depth: diff must touch exactly the declared files, nothing more.
    declared_files = set(candidate.get("files") or [])
    diff_files = set(parse_diff_touched_files(diff_text))
    if diff_files - declared_files:
        return _reject(f"diff touches undeclared files: {sorted(diff_files - declared_files)}")

    # HS4-6: eval surface expansion re-check (defense in depth vs HS3-6).
    eval_reason = eval_surface_gate_reason(candidate, diff_text)
    if eval_reason:
        return _reject(f"HS4-6: {eval_reason}")

    held_in = held_in_scope(candidate, root=root)

    worktree = create_regression_worktree(git_root, label=candidate_id)
    try:
        ok, apply_err = apply_diff(worktree, diff_path)
        if not ok:
            return _reject(f"git apply failed: {apply_err}")

        assertion_results = run_assertions(worktree, assertions_declared)
        held_out = run_held_out(worktree, exclude_topics=held_in["topics"])
        smoke = run_smoke_signal(worktree)

        assertions_pass = all(r.passed for r in assertion_results)
        verdict = "pass" if (assertions_pass and held_out["pass"] and smoke["pass"]) else "fail"
        reason = (
            "all assertions green; held-out + smoke clean"
            if verdict == "pass"
            else "assertion, held-out, or smoke failure — see detail fields"
        )

        report = RegressionGateReport(
            candidate_id=candidate_id,
            held_in=held_in,
            held_out=held_out,
            smoke=smoke,
            resolved_patterns_checked=held_in["source_patterns"],
            eval_surface_expanded=bool(candidate.get("eval_additions")),
            assertions=[asdict(r) for r in assertion_results],
            verdict=verdict,
            reason=reason,
            generated_at=_now_iso(),
        )
        write_report(report, root=root)
        return report
    finally:
        remove_regression_worktree(git_root, worktree)


__all__ = [
    "RegressionRejected",
    "AssertionResult",
    "RegressionGateReport",
    "regression_gate_enabled",
    "resolved_patterns_path",
    "load_resolved_patterns",
    "record_resolved_pattern",
    "held_in_topics_for_tag",
    "held_in_scope",
    "parse_diff_touched_files",
    "diff_introduces_new_flags",
    "diff_touches_manifest",
    "eval_surface_gate_reason",
    "create_regression_worktree",
    "remove_regression_worktree",
    "apply_diff",
    "run_assertions",
    "run_held_out",
    "run_smoke_signal",
    "write_report",
    "load_report",
    "run_regression_gate",
]
