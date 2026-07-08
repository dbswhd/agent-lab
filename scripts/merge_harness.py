#!/usr/bin/env python3
"""HS5 MERGE — offline harness_patch CLI.

Three modes over the same merge_gate.py gates (STOP guard, regression pass,
clean working tree, diff freshness, Tier B full-approval-only):

- ``--mode propose``  create the ``harness_patch`` Human Inbox item in a real
                       session (for web-UI review — approving there routes
                       through ``human_inbox.resolve_inbox_item`` ->
                       ``merge_gate.handle_harness_patch_resolve``).
- ``--mode merge``    apply the candidate directly ("offline script 우선" —
                       running this command *is* the human approval, same as
                       scripts/propose_harness.py / regress_harness.py).
- ``--mode rollback`` git revert a merged candidate's commit and quarantine
                       any playbook bullets stamped with its harness_rev.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_propose(args: argparse.Namespace, root: Path | None) -> int:
    from agent_lab.merge_gate import MergeRejected, propose_harness_patch

    try:
        item = propose_harness_patch(args.candidate_id, Path(args.session_folder), root=root)
    except MergeRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    print(f"inbox item created: {item['id']} (session={args.session_folder})")
    return 0


def run_merge(args: argparse.Namespace, root: Path | None) -> int:
    from agent_lab.merge_gate import MergeRejected, merge_candidate

    git_root = Path(args.git_root) if args.git_root else (root or ROOT)
    try:
        result = merge_candidate(args.candidate_id, git_root=git_root, root=root, dry_run=args.dry_run)
    except MergeRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    print(f"status: {result['status']}")
    if result.get("merge_commit_sha"):
        print(f"merge_commit_sha: {result['merge_commit_sha']}")
        print(f"harness_rev: {result['harness_rev']}")
    return 0


def run_rollback(args: argparse.Namespace, root: Path | None) -> int:
    from agent_lab.merge_gate import MergeRejected, rollback_harness_patch

    git_root = Path(args.git_root) if args.git_root else (root or ROOT)
    try:
        result = rollback_harness_patch(args.candidate_id, git_root=git_root, root=root)
    except MergeRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    print(f"status: {result['status']}")
    print(f"quarantined playbook bullets: {result['quarantined_bullets']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["propose", "merge", "rollback"], required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--root", help="repo root override (기본: 실제 repo root)")
    parser.add_argument("--git-root", help="merge/rollback 대상 git 저장소 (기본: --root 또는 실제 repo root)")
    parser.add_argument("--session-folder", help="--mode propose 전용 — Inbox 카드를 붙일 세션 폴더")
    parser.add_argument("--dry-run", action="store_true", help="--mode merge 전용 — 실제 apply/commit 없이 게이트만 확인")
    args = parser.parse_args()

    from agent_lab.merge_gate import harness_inbox_enabled

    if not harness_inbox_enabled():
        print("AGENT_LAB_HARNESS_INBOX=0 — set =1 to run MERGE.", file=sys.stderr)
        return 2

    root = Path(args.root) if args.root else None

    if args.mode == "propose":
        if not args.session_folder:
            print("--mode propose requires --session-folder", file=sys.stderr)
            return 2
        return run_propose(args, root)
    if args.mode == "merge":
        return run_merge(args, root)
    return run_rollback(args, root)


if __name__ == "__main__":
    sys.exit(main())
