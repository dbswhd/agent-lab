"""CX8 (09-context-engineering.md §11) — collect `context_recipe_shadow`
records across representative mission phases.

`src/agent_lab/context/bundle_shadow.py`'s flag-gated splice
(`AGENT_LAB_CONTEXT_RECIPE`) computes a parallel `select_context()`-based
manifest and stamps a comparison dict into `run_meta["context_recipe_shadow"]`
— but only when a real agent turn actually runs through `build_context_bundle`/
`build_slim_consensus_bundle`. This script drives those two functions
directly (no Room/mock-agent loop needed — they only need `messages` +
`run_meta`, not a live model call) across one scenario per mapped mission
phase, using the real repo root as the workspace so repo-tree/AGENTS.md
producers see actual files instead of empty stubs, and reports what got
recorded.

This does not judge parity quality or recommend a cutover decision — it
only collects and prints the raw `context_recipe_shadow` records plus a
few derived rollups (success rate, included-source frequency, phases that
skip because the phase has no ActivityKind mapping) so a human/dogfood
harness has real data to review before the CX8 discussion's next step.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
os.environ["AGENT_LAB_CONTEXT_RECIPE"] = "1"


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


SAMPLE_PLAN = """# Demo feature

## 지금 실행

1. Add a health check endpoint
   - 무엇을: implement /health route
   - 어디서: `app/server/routers/health.py`
   - 검증: `pytest tests/test_health.py`

## 진행 중 미결

- confirm rate limit for the new endpoint
"""


def _messages() -> list[_Msg]:
    return [
        _Msg("user", None, "add a health check endpoint and make sure it's fast", ts="2026-07-16T00:00:00Z"),
        _Msg("agent", "claude", "I'll add /health under app/server/routers/.", 1, ts="2026-07-16T00:00:01Z"),
        _Msg("agent", "codex", "Agreed, keeping it dependency-free for speed.", 1, ts="2026-07-16T00:00:02Z"),
    ]


def _run_meta(phase: str, *, enabled: bool = True) -> dict[str, Any]:
    return {
        "workspace_binding": {"path": str(ROOT)},
        "mission_loop": {"enabled": enabled, "phase": phase},
        "goal_ledger": [
            {"event": "plan approved", "phase": "plan", "note": "v1"},
            {"event": "execution started", "phase": "execute"},
        ],
        "turn_state": {},
        # CRITIC/REPAIR/SCRIBE all require SourceClass.EVIDENCE
        # (activity_recipes.py) -- without at least one recorded artifact,
        # those three always fail with "missing required sources: evidence"
        # regardless of anything else, which would make this dogfood run
        # look like a recipe-pipeline problem when it's actually just a
        # missing-fixture problem. One representative artifact lets those
        # phases exercise their real path too.
        "artifacts": [
            {
                "id": "art-dogfood-1",
                "producer": "claude",
                "kind": "diff",
                "summary": "added /health route returning 200 with no dependencies",
                "ts": "2026-07-16T00:00:03Z",
            }
        ],
    }


# Every MissionPhase this repo's context/bundle_recipe.py::activity_kind_for_
# mission_phase either maps to an ActivityKind, or deliberately leaves
# unmapped (see that module's own comment for why) -- both are worth
# recording, since an unmapped phase should always skip cleanly, not error.
SCENARIOS: list[tuple[str, str]] = [
    ("clarify", "CLARIFY"),
    ("discuss", "DISCUSS"),
    ("plan_gate", "PLAN_GATE"),
    ("plan_reject", "PLAN_REJECT"),
    ("execute_queue", "EXECUTE_QUEUE"),
    ("dry_run", "DRY_RUN"),
    ("merge_review", "MERGE_REVIEW"),
    ("verify", "VERIFY"),
    ("repair", "REPAIR"),
    ("mission_define", "MISSION_DEFINE"),
    ("mission_done", "MISSION_DONE"),
]


def run_dogfood(*, agent: str = "claude") -> dict[str, Any]:
    from agent_lab.context.bundle import build_context_bundle

    records: list[dict[str, Any]] = []
    for scenario_id, phase in SCENARIOS:
        run_meta = _run_meta(phase)
        bundle = build_context_bundle(
            "add a health check endpoint",
            _messages(),
            agent,
            plan_md=SAMPLE_PLAN,
            run_meta=run_meta,
            format_thread=_format_thread,
        )
        shadow = run_meta.get("context_recipe_shadow")
        records.append(
            {
                "scenario": scenario_id,
                "phase": phase,
                "legacy_render_chars": len(bundle.render()),
                "slim_context": bundle.meta.slim_context,
                "shadow": shadow,
            }
        )

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
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", default="claude", help="agent id to build context for (default: claude)")
    parser.add_argument("--out", type=Path, help="optional path to also write the JSON report to")
    args = parser.parse_args()

    report = run_dogfood(agent=args.agent)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
