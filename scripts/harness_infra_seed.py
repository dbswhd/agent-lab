#!/usr/bin/env python3
"""Seed real ``harness_infra`` outcome rows to test the HS3 PROPOSE path end-to-end.

HS1 MINE (``weakness_miner.mine_weakness_patterns``) only flags a pattern
``addressable`` once it recurs across >= ``MIN_PATTERN_SAMPLE`` (3) *distinct
sessions*. As of 2026-07-14, ``.agent-lab/outcomes.jsonl`` has 82 rows across
13 sessions but zero carry a ``primary_tag`` — every recorded session so far
came from cooperative mock dogfooding that never hit any of the three HS1-1
failure tags (see ``scripts/propose_harness.py --mode list``).

This script manufactures the *real* signal rather than hand-writing ledger
rows: it builds a genuine ``PlanAction`` with a missing ``검증:`` field, runs
it through the actual ``plan.execute_merge.oracle_verify`` (which returns the
production "skipped / verify field missing" result — see
``tests/test_oracle_verify.py::test_oracle_verify_skips_missing_verify``),
then appends it via the actual ``outcome_harvester.record_execute_outcome``
(same call ``_record_verify_after_merge`` makes after a real merge — see
``tests/test_outcome_harvester_execute.py::
test_record_execute_outcome_tags_harness_infra_on_skipped_verdict``). The
only thing skipped is running a full multi-agent Room turn + worktree merge
to *produce* the plan action — everything downstream of "here is an action
with no verify criterion" is real production code.

Writes N session folders under ``sessions/`` (gitignored, not committed —
same as any other local session) and appends N rows to the real
``.agent-lab/outcomes.jsonl`` (also gitignored). Same ``category`` across all
N so they collapse into one ``fp:harness_infra:{category}`` pattern.

Usage:
    python scripts/harness_infra_seed.py [--count 3] [--category quick]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SESSION_PREFIX = "hs3-seed-harness-infra"


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_seed_run(folder: Path, *, category: str, topic: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    run = {
        "topic": topic,
        "turns": [
            {
                "agents": ["cursor", "codex", "claude"],
                "agent_parallel_rounds": 1,
                "consensus": {"status": "reached"},
                "category": {"value": category, "source": "heuristic"},
                "roles": {"cursor": "proposer", "codex": "executor", "claude": "critic"},
            }
        ],
        "objections": [],
        "executions": [],
    }
    (folder / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_one(index: int, *, category: str) -> Path:
    from agent_lab.outcome_harvester import record_execute_outcome
    from agent_lab.plan.actions import PlanAction
    from agent_lab.plan.execute_merge import oracle_verify

    session_id = f"{_now_stamp()}-{SESSION_PREFIX}-{index}"
    folder = ROOT / "sessions" / session_id
    topic = f"HS3 seed #{index} — deliberately missing 검증: criterion (harness_infra probe)"
    _write_seed_run(folder, category=category, topic=topic)

    # Real PlanAction with no verify criterion — "-" is what plan.actions'
    # FIELD_VERIFY parser leaves behind for an omitted 검증: line (see
    # tests/test_oracle_verify.py::_action).
    action = PlanAction(
        index=1,
        what="Seed action for HS3 dogfood — no real change",
        where="`docs/HS3-SEED-PLACEHOLDER.md`",
        verify="-",
        refs=(),
        raw="",
        kind="now",
    )
    result = oracle_verify(action, ["docs/HS3-SEED-PLACEHOLDER.md"], workspace_root=folder)
    assert result["verdict"] == "skipped", f"expected real oracle_verify to skip, got {result!r}"

    execution = {
        "id": f"{session_id}-exec",
        "oracle": result,
        "repair_history": [],
    }
    record_execute_outcome(folder, execution)
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--count", type=int, default=3, help="distinct sessions to seed (default 3 = MIN_PATTERN_SAMPLE)"
    )
    parser.add_argument(
        "--category", default="quick", help="shared category so rows collapse into one pattern (default quick)"
    )
    args = parser.parse_args()

    os.environ.setdefault("AGENT_LAB_OUTCOME_LEDGER", "1")

    folders = [_seed_one(i, category=args.category) for i in range(1, args.count + 1)]

    from agent_lab.weakness_miner import mine_weakness_patterns

    report = mine_weakness_patterns(ROOT)
    print(f"seeded {len(folders)} session(s):")
    for f in folders:
        print(f"  {f.relative_to(ROOT)}")
    print()
    print(
        f"mine_weakness_patterns() -> {len(report['patterns'])} pattern(s), min_pattern_sample={report['min_pattern_sample']}"
    )
    for p in report["patterns"]:
        marker = "ADDRESSABLE" if p["addressable"] else "-"
        print(f"  [{marker}] {p['pattern_id']}  recurrence={p['recurrence_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
