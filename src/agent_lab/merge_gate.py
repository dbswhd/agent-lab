"""HS5 MERGE — harness_patch Inbox gate + main-tree commit + rollback/quarantine.

Flag-gated (``AGENT_LAB_HARNESS_INBOX``, default off). See
docs/DESIGN-HARNESS-SELF-IMPROVE.md §7.2, §8.4, §9 HS5.

The only place in the HSIL pipeline that writes to the real git tree.
Layered before that write, in order:

1. Regression must have passed (``regression_gate.load_report`` verdict).
2. STOP guard re-checked (conditions may have changed since PROPOSE/REGRESS).
3. Tier B never accepts ``used_light_approval`` (HS5-B2 — full Inbox only);
   Tier A light approval additionally requires autonomy level L2+ (HS5-3,
   ``autonomy_promotion.harness_patch_light_approval_eligible``).
4. Working tree must be clean (``plan.execute_git.is_working_tree_clean``).
5. The diff must still apply cleanly against current HEAD (freshness check —
   the codebase may have drifted since REGRESS ran against a worktree).
6. Tier B candidates touching the eval surface get an additional removal
   audit (HS5-B3) — only additions are allowed, not silent deletion of an
   existing held-out case.

Every disposition (merged, rejected, rolled back) is recorded in
``candidates/{id}/merge_record.json`` — a single current-state file
(overwritten on retry), distinct from the immutable ``candidate.json`` and
``regression_report.json`` written by earlier stages.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TRUE = frozenset({"1", "true", "yes", "on"})
MERGE_RECORD_SCHEMA_VERSION = 1
PREDICTIONS_SCHEMA_VERSION = 1


def harness_inbox_enabled() -> bool:
    """AGENT_LAB_HARNESS_INBOX (default off)."""
    return (os.getenv("AGENT_LAB_HARNESS_INBOX") or "").strip().lower() in _TRUE


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MergeRejected(Exception):
    """A candidate failed a MERGE-time gate (STOP guard, tier, freshness, audit)."""


# ---------------------------------------------------------------------------
# merge_record.json (per-candidate current disposition)
# ---------------------------------------------------------------------------


@dataclass
class MergeRecord:
    candidate_id: str
    status: str  # "merged" | "rejected" | "rolled_back"
    reason: str
    merge_commit_sha: str | None
    harness_rev: str | None
    updated_at: str


def _merge_record_path(candidate_id: str, *, root: Path | None = None) -> Path:
    from agent_lab.harness_proposer import candidates_root

    return candidates_root(root) / candidate_id / "merge_record.json"


def _write_merge_record(
    candidate_id: str,
    *,
    status: str,
    reason: str,
    root: Path | None = None,
    merge_commit_sha: str | None = None,
    harness_rev: str | None = None,
) -> Path:
    record = MergeRecord(
        candidate_id=candidate_id,
        status=status,
        reason=reason,
        merge_commit_sha=merge_commit_sha,
        harness_rev=harness_rev,
        updated_at=_now_iso(),
    )
    path = _merge_record_path(candidate_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"v": MERGE_RECORD_SCHEMA_VERSION, **asdict(record)}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_merge_record(candidate_id: str, *, root: Path | None = None) -> dict[str, Any] | None:
    path = _merge_record_path(candidate_id, root=root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# HS5-4 predictions.jsonl
# ---------------------------------------------------------------------------


def predictions_path(root: Path | None = None) -> Path:
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "harness" / "predictions.jsonl"


def load_predictions(root: Path | None = None) -> list[dict[str, Any]]:
    """Fold the append-only ledger to current state (latest row per candidate_id)."""
    path = predictions_path(root)
    if not path.is_file():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("candidate_id"):
            latest[str(row["candidate_id"])] = row
    return list(latest.values())


def record_prediction(
    candidate_id: str, *, predicted_effect: dict[str, Any], root: Path | None = None
) -> None:
    """HS5-4 — one row at merge time; ``verify_prediction`` appends the
    observed-outcome revision later (append-only, last write wins on read)."""
    path = predictions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "v": PREDICTIONS_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "predicted_effect": predicted_effect,
        "actual_effect": None,
        "verified": None,
        "merged_at": _now_iso(),
        "verified_at": None,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def verify_prediction(
    candidate_id: str, *, verified: bool, actual_effect: dict[str, Any] | None = None, root: Path | None = None
) -> None:
    """Manual — a prediction can only be verified once real outcome data
    exists (dogfood/feedback_report observation), which this module doesn't
    auto-detect (out of scope while dogfood is paused — see NOW.md)."""
    existing = {p["candidate_id"]: p for p in load_predictions(root)}
    base = existing.get(candidate_id)
    if base is None:
        raise MergeRejected(f"no prediction recorded for {candidate_id}")
    path = predictions_path(root)
    row = {
        **base,
        "actual_effect": actual_effect,
        "verified": verified,
        "verified_at": _now_iso(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# HS5-6 — current harness revision resolver
# ---------------------------------------------------------------------------


def current_harness_rev(root: Path | None = None) -> str:
    """Git SHA of HEAD — the "current harness revision" playbook bullets and
    (later) failure_pattern episodes get stamped with. Fail-open: returns
    HARNESS_REV_UNSET if git isn't available (never blocks the caller)."""
    from agent_lab.wisdom.playbook import HARNESS_REV_UNSET

    try:
        from agent_lab.plan.execute_git import detect_git_root
        from agent_lab.regression_gate import _run_git

        start = Path(root) if root is not None else Path.cwd()
        git_root = detect_git_root(start)
        if git_root is None:
            return HARNESS_REV_UNSET
        proc = _run_git(git_root, "rev-parse", "HEAD", check=False)
        sha = (proc.stdout or "").strip()
        return f"manifest@sha:{sha}" if sha else HARNESS_REV_UNSET
    except Exception:
        return HARNESS_REV_UNSET


# ---------------------------------------------------------------------------
# HS5-B3 — eval case removal audit
# ---------------------------------------------------------------------------

_EVAL_SURFACE_FILES = ("evals/cases.jsonl", "sessions/_benchmark/topics/dogfood-v1.json")
_REMOVED_ID_RE = re.compile(r'^-\s*\{.*?"id"\s*:\s*"([^"]+)"', re.MULTILINE)


def audit_eval_case_diff(diff_text: str) -> str | None:
    """HS5-B3 — reject a diff that *removes* an existing eval case id from a
    held-out surface file; only additions are allowed. None means it passes."""
    from agent_lab.regression_gate import parse_diff_touched_files

    touched = set(parse_diff_touched_files(diff_text))
    if not touched & set(_EVAL_SURFACE_FILES):
        return None
    removed_ids = _REMOVED_ID_RE.findall(diff_text)
    if removed_ids:
        return f"diff removes existing eval case id(s) {removed_ids} — held-out freeze violation"
    return None


# ---------------------------------------------------------------------------
# HS5-1 — propose the Inbox item
# ---------------------------------------------------------------------------


def propose_harness_patch(candidate_id: str, folder: Path, *, root: Path | None = None) -> dict[str, Any]:
    """Create the ``harness_patch`` Inbox item — refuses a candidate without
    a passing regression report (MERGE never proposes what REGRESS rejected)."""
    from agent_lab.harness_proposer import load_candidate
    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.regression_gate import load_report

    candidate = load_candidate(candidate_id, root=root)
    report = load_report(candidate_id, root=root)
    if report is None or report.get("verdict") != "pass":
        raise MergeRejected(f"candidate {candidate_id} has no passing regression report")

    tier = str(candidate.get("tier") or "")
    prompt = f"Harness patch 승인 요청: {candidate_id} (axis={candidate.get('axis')}, tier={tier})"
    summary = f"pattern={candidate.get('pattern_id')} files={candidate.get('files')}"
    return create_inbox_item(
        folder,
        kind="harness_patch",
        source="merge_gate",
        prompt=prompt,
        summary=summary,
        options=[{"id": "approve", "label": "머지 승인"}, {"id": "reject", "label": "거부"}],
        refs=[candidate_id, f"editable_tier:{tier}"],
    )


# ---------------------------------------------------------------------------
# HS5-2/B2 — resolve dispatch target (wired from human_inbox.resolve_inbox_item)
# ---------------------------------------------------------------------------


def handle_harness_patch_resolve(
    folder: Path,
    item: dict[str, Any],
    *,
    selected: list[str] | None,
    status: str,
    git_root: Path | None = None,
    used_light_approval: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    if item.get("kind") != "harness_patch":
        return {}
    refs = list(item.get("refs") or [])
    candidate_id = str(refs[0]) if refs else ""
    if not candidate_id:
        return {}

    if status in ("rejected", "superseded"):
        _write_merge_record(candidate_id, status="rejected", reason=f"inbox status={status}", root=root)
        return {"status": "rejected"}

    choice = (selected or [""])[0].strip().lower()
    if choice != "approve":
        _write_merge_record(candidate_id, status="rejected", reason=f"choice={choice!r}", root=root)
        return {"status": "rejected"}

    from agent_lab.harness_proposer import load_candidate
    from agent_lab.plan.execute_git import detect_git_root

    candidate = load_candidate(candidate_id, root=root)
    tier = str(candidate.get("tier") or "")
    if used_light_approval:
        if tier == "B":
            raise MergeRejected("HS5-B2: Tier B requires full Inbox approval, not L2 lightweight")
        from agent_lab.autonomy_promotion import harness_patch_light_approval_eligible
        from agent_lab.run.meta import read_run_meta

        if not harness_patch_light_approval_eligible(read_run_meta(folder)):
            _write_merge_record(
                candidate_id, status="rejected", reason="HS5-3: light approval requires autonomy L2+", root=root
            )
            raise MergeRejected("HS5-3: light approval requires autonomy level L2 or higher")

    resolved_git_root = git_root or detect_git_root(folder)
    if resolved_git_root is None:
        _write_merge_record(candidate_id, status="rejected", reason="no git root detected", root=root)
        raise MergeRejected("no git root detected for merge")

    return merge_candidate(candidate_id, git_root=resolved_git_root, root=root)


# ---------------------------------------------------------------------------
# the actual write — apply + commit
# ---------------------------------------------------------------------------


def merge_candidate(
    candidate_id: str, *, git_root: Path, root: Path | None = None, dry_run: bool = False
) -> dict[str, Any]:
    from agent_lab.harness_proposer import load_candidate, stop_guard_reason
    from agent_lab.plan.execute_git import is_working_tree_clean
    from agent_lab.regression_gate import _run_git, apply_diff, load_report, record_resolved_pattern

    reason = stop_guard_reason()
    if reason:
        _write_merge_record(candidate_id, status="rejected", reason=f"STOP guard: {reason}", root=root)
        raise MergeRejected(f"STOP guard: {reason}")

    candidate = load_candidate(candidate_id, root=root)
    report = load_report(candidate_id, root=root)
    if report is None or report.get("verdict") != "pass":
        _write_merge_record(candidate_id, status="rejected", reason="no passing regression report", root=root)
        raise MergeRejected(f"candidate {candidate_id} has no passing regression report")

    if not is_working_tree_clean(git_root):
        _write_merge_record(candidate_id, status="rejected", reason="git_root working tree dirty", root=root)
        raise MergeRejected(f"git root has uncommitted changes: {git_root}")

    diff_ref = str(candidate.get("diff_ref") or "")
    diff_path = Path(diff_ref)
    if not diff_path.is_absolute() and root is not None:
        diff_path = Path(root) / diff_path

    if str(candidate.get("tier") or "") == "B" and diff_path.is_file():
        audit_reason = audit_eval_case_diff(diff_path.read_text(encoding="utf-8"))
        if audit_reason:
            _write_merge_record(candidate_id, status="rejected", reason=f"HS5-B3: {audit_reason}", root=root)
            raise MergeRejected(f"HS5-B3: {audit_reason}")

    if dry_run:
        return {"status": "dry_run", "candidate_id": candidate_id}

    # Freshness check: the codebase may have drifted since REGRESS applied
    # this same diff to a throwaway worktree — re-verify against current HEAD.
    ok, err = apply_diff(git_root, diff_path)
    if not ok:
        _write_merge_record(
            candidate_id, status="rejected", reason=f"git apply failed (drift since regress?): {err}", root=root
        )
        raise MergeRejected(f"git apply failed: {err}")

    files = list(candidate.get("files") or [])
    _run_git(git_root, "add", *files)
    _run_git(git_root, "commit", "-m", f"harness_patch: {candidate_id} ({candidate.get('pattern_id')})")
    merge_sha = _run_git(git_root, "rev-parse", "HEAD").stdout.strip()
    harness_rev = f"manifest@sha:{merge_sha}"

    record_resolved_pattern(str(candidate.get("pattern_id") or ""), candidate_id=candidate_id, root=root)
    record_prediction(candidate_id, predicted_effect={"pattern_id": candidate.get("pattern_id")}, root=root)
    _write_merge_record(
        candidate_id,
        status="merged",
        reason="approved via Inbox",
        root=root,
        merge_commit_sha=merge_sha,
        harness_rev=harness_rev,
    )
    return {"status": "merged", "merge_commit_sha": merge_sha, "harness_rev": harness_rev}


# ---------------------------------------------------------------------------
# HS5-7 — rollback + quarantine
# ---------------------------------------------------------------------------


def rollback_harness_patch(candidate_id: str, *, git_root: Path, root: Path | None = None) -> dict[str, Any]:
    from agent_lab.regression_gate import _run_git
    from agent_lab.wisdom.playbook import quarantine_bullets_by_harness_rev

    record = load_merge_record(candidate_id, root=root)
    if record is None or record.get("status") != "merged":
        raise MergeRejected(f"candidate {candidate_id} was never merged")
    merge_sha = record.get("merge_commit_sha")
    harness_rev = record.get("harness_rev")
    if not merge_sha:
        raise MergeRejected(f"candidate {candidate_id} has no merge_commit_sha to revert")

    proc = _run_git(git_root, "revert", "--no-edit", str(merge_sha), check=False)
    if proc.returncode != 0:
        raise MergeRejected(f"git revert failed: {proc.stderr}")

    quarantined = quarantine_bullets_by_harness_rev(str(harness_rev), root=root) if harness_rev else []
    _write_merge_record(
        candidate_id,
        status="rolled_back",
        reason="human-initiated rollback",
        root=root,
        merge_commit_sha=merge_sha,
        harness_rev=harness_rev,
    )
    return {"status": "rolled_back", "quarantined_bullets": quarantined}


# ---------------------------------------------------------------------------
# HS5-5 — KPI aggregation
# ---------------------------------------------------------------------------


def harness_patch_stats(root: Path | None = None) -> dict[str, Any]:
    """accept_rate over Inbox-resolved candidates; prediction_accuracy over
    manually-verified predictions. Both None until enough data exists."""
    from agent_lab.harness_proposer import candidates_root

    records: list[dict[str, Any]] = []
    base = candidates_root(root)
    if base.is_dir():
        for candidate_dir in base.iterdir():
            record = load_merge_record(candidate_dir.name, root=root)
            if record is not None:
                records.append(record)

    decided = [r for r in records if r.get("status") in ("merged", "rejected")]
    merged = [r for r in decided if r.get("status") == "merged"]
    accept_rate = round(len(merged) / len(decided), 4) if decided else None

    predictions = load_predictions(root)
    verified_rows = [p for p in predictions if p.get("verified") is not None]
    accurate = [p for p in verified_rows if p.get("verified") is True]
    prediction_accuracy = round(len(accurate) / len(verified_rows), 4) if verified_rows else None

    return {
        "candidates_decided": len(decided),
        "candidates_merged": len(merged),
        "accept_rate": accept_rate,
        "predictions_total": len(predictions),
        "predictions_verified": len(verified_rows),
        "prediction_accuracy": prediction_accuracy,
    }


__all__ = [
    "MergeRejected",
    "MergeRecord",
    "harness_inbox_enabled",
    "load_merge_record",
    "predictions_path",
    "load_predictions",
    "record_prediction",
    "verify_prediction",
    "current_harness_rev",
    "audit_eval_case_diff",
    "propose_harness_patch",
    "handle_harness_patch_resolve",
    "merge_candidate",
    "rollback_harness_patch",
    "harness_patch_stats",
]
