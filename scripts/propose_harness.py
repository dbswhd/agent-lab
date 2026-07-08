#!/usr/bin/env python3
"""HS3-5 — offline harness-patch proposer CLI (primary PROPOSE entry point).

"proposer: offline script 우선; Room optional" (docs/DESIGN-HARNESS-SELF-IMPROVE.md
§9 HS3). This script does not generate diff content or call an LLM — a human
(or a future Room agent) authors the change and submits it here for validation
against the STOP guard / tier / axis / eval-surface gates
(``harness_proposer.propose_candidate``).

모드:
- ``--mode list``     (기본) HS1 MINE의 addressable weakness pattern 목록 +
                       현재 STOP guard 상태를 보여준다 (HS3-4 trigger 확인용).
- ``--mode propose``   후보를 검증하고 ``.agent-lab/harness/candidates/{id}/``에
                       기록한다. 거부되면 사유와 함께 종료코드 1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_list(root: Path | None) -> int:
    from agent_lab.harness_proposer import addressable_patterns, ensure_manifest, stop_guard_reason

    ensure_manifest(root)
    reason = stop_guard_reason()
    if reason:
        print(f"STOP guard ACTIVE — proposer disabled: {reason}")
    else:
        print("STOP guard clear — proposer may run.")

    patterns = addressable_patterns(root=root)
    if not patterns:
        print("\nno addressable weakness patterns yet (recurrence_count >= MIN_PATTERN_SAMPLE required).")
        return 0

    print(f"\n{len(patterns)} addressable pattern(s):")
    for p in patterns:
        print(f"  {p['pattern_id']}  recurrence={p['recurrence_count']}  primary_tag={p['primary_tag']}")
    return 0


def run_propose(args: argparse.Namespace, root: Path | None) -> int:
    from agent_lab.harness_proposer import ProposalRejected, propose_candidate, write_candidate

    files = [f.strip() for f in args.files.split(",") if f.strip()]
    eval_additions = [e.strip() for e in (args.eval_additions or "").split(",") if e.strip()]
    assertions = [a.strip() for a in (args.assertions or "").split(",") if a.strip()]
    try:
        candidate = propose_candidate(
            pattern_id=args.pattern_id,
            axis=args.axis,
            files=files,
            diff_ref=args.diff_ref,
            eval_additions=eval_additions,
            assertions=assertions,
            introduces_new_surface=args.introduces_new_surface,
            block=args.block,
            root=root,
        )
    except ProposalRejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1

    path = write_candidate(candidate, root=root)
    print(f"proposed: {candidate.id} (tier={candidate.tier}, axis={candidate.axis})")
    print(f"written: {path}")
    if not candidate.assertions:
        print("warning: no --assertions declared — HS4 REGRESS will reject this candidate (HS4-1).", file=sys.stderr)
    print("next: scripts/regress_harness.py --candidate-id " + candidate.id + " --diff-path <diff> (HS4 REGRESS).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["list", "propose"], default="list")
    parser.add_argument("--root", help="repo root override (기본: 실제 repo root)")
    parser.add_argument("--pattern-id", help="mine_weakness_patterns()의 pattern_id (예: fp:weak_taste:standard)")
    parser.add_argument("--axis", help="prompts|preset|profile|skills|hooks|ui|eval_surface 중 하나")
    parser.add_argument("--files", help="쉼표 구분 터치 파일 목록")
    parser.add_argument("--diff-ref", help="diff 파일 경로 또는 참조 문자열")
    parser.add_argument("--eval-additions", help="쉼표 구분 dogfood topic id 또는 evals case id")
    parser.add_argument(
        "--assertions", help="쉼표 구분 pytest node id (HS4-1 REGRESS의 결정론적 게이트 — 없으면 HS4에서 거부)"
    )
    parser.add_argument("--introduces-new-surface", action="store_true", help="신규 glob/블록/플래그 도입 시 지정")
    parser.add_argument("--block", help="edit_unit=block 대상(prompts.py)일 때 agent 이름")
    args = parser.parse_args()

    root = Path(args.root) if args.root else None

    if args.mode == "list":
        return run_list(root)

    missing = [
        name
        for name, val in (
            ("--pattern-id", args.pattern_id),
            ("--axis", args.axis),
            ("--files", args.files),
            ("--diff-ref", args.diff_ref),
        )
        if not val
    ]
    if missing:
        print(f"--mode propose requires: {', '.join(missing)}", file=sys.stderr)
        return 2
    return run_propose(args, root)


if __name__ == "__main__":
    sys.exit(main())
