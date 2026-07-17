"""CX8 (09-context-engineering.md §11) — collect `context_recipe_shadow`
records across representative mission phases AND multiple input variants
per activity.

`src/agent_lab/context/bundle_shadow.py`'s flag-gated splice
(`AGENT_LAB_CONTEXT_RECIPE`) computes a parallel `select_context()`-based
manifest and stamps a comparison dict into `run_meta["context_recipe_shadow"]`
— but only when a real agent turn actually runs through `build_context_bundle`/
`build_slim_consensus_bundle`. This script drives those two functions
directly (no Room/mock-agent loop needed — they only need `messages` +
`run_meta`, not a live model call), using the real repo root as the
workspace so repo-tree/AGENTS.md producers see actual files, and reports
what got recorded.

2026-07-16 — expanded from the first pass's 11 single-variant phase
scenarios (docs/redesign-2026-07/evidence/cx8-context-recipe-shadow-dogfood-
2026-07-16.md's own "다음 단계" #1) to also vary, per activity-mapped phase:
message-history size (baseline / long / minimal), artifact count (0 / 1 /
5), self-agent identity (claude / codex), and whether team_task/objection/
mailbox producers have anything to say — the first pass's synthetic
run_meta left all three empty, so none of that content ever showed up in
`included_sources`. The 2 genuinely-unmapped phases (MISSION_DEFINE,
MISSION_DONE) stay single-variant; there's nothing to vary when the whole
point is confirming a clean skip.

This does not judge parity quality or recommend a cutover decision — it
only collects and prints the raw `context_recipe_shadow` records plus
derived rollups (success rate, included-source frequency across the full
sample, per-activity token/char stats) so a human/dogfood harness has more
real data to review before the CX8 discussion's next step.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
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


def _baseline_messages() -> list[_Msg]:
    return [
        _Msg("user", None, "add a health check endpoint and make sure it's fast", ts="2026-07-16T00:00:00Z"),
        _Msg("agent", "claude", "I'll add /health under app/server/routers/.", 1, ts="2026-07-16T00:00:01Z"),
        _Msg("agent", "codex", "Agreed, keeping it dependency-free for speed.", 1, ts="2026-07-16T00:00:02Z"),
    ]


def _long_messages() -> list[_Msg]:
    """~10 turns across 2 rounds -- exercises turn_bridge (R1 summary before
    round 2) and peer_block (round-2 peer chatter) more than the 3-message
    baseline ever could."""
    msgs = [_Msg("user", None, "add a health check endpoint and make sure it's fast", ts="2026-07-16T00:00:00Z")]
    for i, (agent, text) in enumerate(
        [
            ("claude", "I'll add /health under app/server/routers/."),
            ("codex", "Agreed, keeping it dependency-free for speed."),
            ("cursor", "Should we also check DB connectivity in the handler?"),
        ]
    ):
        msgs.append(_Msg("agent", agent, text, 1, ts=f"2026-07-16T00:00:{i + 1:02d}Z"))
    msgs.append(_Msg("user", None, "yes, add a lightweight DB ping too", ts="2026-07-16T00:00:10Z"))
    for i, (agent, text) in enumerate(
        [
            ("claude", "Added a DB ping with a 200ms timeout."),
            ("codex", "LGTM, matches the existing pool timeout convention."),
            ("cursor", "One more thing -- should this bypass auth middleware?"),
            ("claude", "Yes, /health should be unauthenticated."),
        ]
    ):
        msgs.append(_Msg("agent", agent, text, 2, ts=f"2026-07-16T00:00:{i + 11:02d}Z"))
    return msgs


def _minimal_messages() -> list[_Msg]:
    return [_Msg("user", None, "add a health check endpoint", ts="2026-07-16T00:00:00Z")]


def _artifacts(count: int) -> list[dict[str, Any]]:
    summaries = [
        "added /health route returning 200 with no dependencies",
        "wrote a unit test for the /health route",
        "added a DB ping with a 200ms timeout",
        "confirmed /health bypasses auth middleware",
        "measured p99 latency at 4ms under load",
    ]
    return [
        {
            "id": f"art-dogfood-{i + 1}",
            "producer": "claude",
            "kind": "diff",
            "summary": summaries[i % len(summaries)],
            "ts": f"2026-07-16T00:01:{i:02d}Z",
        }
        for i in range(count)
    ]


@dataclass
class Variant:
    variant_id: str
    messages: list[_Msg] = field(default_factory=_baseline_messages)
    plan_md: str = SAMPLE_PLAN
    artifact_count: int = 1
    agent: str = "claude"
    populate_room_state: bool = False
    """team_task/objection/mailbox producers all read from separate run_meta
    keys (`tasks`/`objections`/`mailbox`) the first dogfood pass never
    populated -- so RUNTIME_STATE/AGENT_OPINION content from those three
    specifically never appeared in that pass's included_sources at all.
    Turning this on seeds all three so this pass can actually observe
    whether they get included."""


VARIANTS: list[Variant] = [
    Variant("baseline"),
    Variant("long_conversation", messages=_long_messages()),
    Variant("minimal", messages=_minimal_messages(), plan_md="", artifact_count=0),
    Variant("many_artifacts", artifact_count=5),
    Variant("different_agent", agent="codex"),
    Variant("room_state_populated", populate_room_state=True),
]


def _run_meta(phase: str, variant: Variant, *, enabled: bool = True) -> dict[str, Any]:
    run_meta: dict[str, Any] = {
        "workspace_binding": {"path": str(ROOT)},
        "mission_loop": {"enabled": enabled, "phase": phase},
        "goal_ledger": [
            {"event": "plan approved", "phase": "plan", "note": "v1"},
            {"event": "execution started", "phase": "execute"},
        ],
        "turn_state": {},
        # CRITIC/REPAIR/SCRIBE all require SourceClass.EVIDENCE
        # (activity_recipes.py) -- without at least one recorded artifact,
        # those three always fail with "missing required sources: evidence",
        # which reads as a recipe-pipeline problem when it's really a
        # missing-fixture problem. See the "minimal" variant for the
        # deliberate negative case instead (artifact_count=0 everywhere).
        "artifacts": _artifacts(variant.artifact_count),
    }
    if variant.populate_room_state:
        run_meta["tasks"] = [
            {"id": "task-1", "title": "add /health route", "status": "in_progress", "owner_agent": "claude"},
            {"id": "task-2", "title": "write /health tests", "status": "pending", "owner_agent": None},
        ]
        run_meta["objections"] = [
            {
                "id": "obj-1", "from": "codex", "act": "CHALLENGE", "status": "open",
                "body": "should /health also report DB connectivity, not just process liveness?",
                "turn": 1, "ts": "2026-07-16T00:00:05Z",
            }
        ]
        run_meta["mailbox"] = [
            {
                "id": "mail-1", "from": "codex", "to": variant.agent,
                "body": "left a comment on the /health PR about timeout handling", "ts": "2026-07-16T00:00:06Z",
                "read": False,
            }
        ]
    return run_meta


# Every MissionPhase this repo's context/bundle_recipe.py::activity_kind_for_
# mission_phase either maps to an ActivityKind, or deliberately leaves
# unmapped (see that module's own comment for why). One representative
# phase per activity gets the full variant sweep; DISCUSS/PLAN_GATE/
# PLAN_REJECT (all -> PLAN) and EXECUTE_QUEUE/DRY_RUN (both -> EXECUTE) and
# MERGE_REVIEW/VERIFY (both -> CRITIC) are otherwise redundant, so they keep
# a single baseline-variant check instead of the full sweep, just to
# confirm the phase-spelling equivalence still holds.
ACTIVITY_PHASES: list[tuple[str, str]] = [
    ("clarify", "CLARIFY"),
    ("plan", "DISCUSS"),
    ("execute", "EXECUTE_QUEUE"),
    ("critic", "MERGE_REVIEW"),
    ("repair", "REPAIR"),
]
EQUIVALENCE_PHASES: list[tuple[str, str]] = [
    ("plan_gate", "PLAN_GATE"),
    ("plan_reject", "PLAN_REJECT"),
    ("dry_run", "DRY_RUN"),
    ("verify", "VERIFY"),
]
UNMAPPED_PHASES: list[tuple[str, str]] = [
    ("mission_define", "MISSION_DEFINE"),
    ("mission_done", "MISSION_DONE"),
]


def _run_one(phase: str, variant: Variant) -> dict[str, Any]:
    from agent_lab.context.bundle import build_context_bundle

    run_meta = _run_meta(phase, variant)
    bundle = build_context_bundle(
        "add a health check endpoint",
        variant.messages,
        variant.agent,
        plan_md=variant.plan_md,
        run_meta=run_meta,
        format_thread=_format_thread,
    )
    return {
        "phase": phase,
        "variant": variant.variant_id,
        "agent": variant.agent,
        "legacy_render_chars": len(bundle.render()),
        "slim_context": bundle.meta.slim_context,
        "shadow": run_meta.get("context_recipe_shadow"),
    }


def run_dogfood() -> dict[str, Any]:
    records: list[dict[str, Any]] = []

    for activity_id, phase in ACTIVITY_PHASES:
        for variant in VARIANTS:
            records.append({"scenario": f"{activity_id}:{variant.variant_id}", **_run_one(phase, variant)})

    baseline = VARIANTS[0]
    for scenario_id, phase in EQUIVALENCE_PHASES:
        records.append({"scenario": f"{scenario_id}:baseline", **_run_one(phase, baseline)})
    for scenario_id, phase in UNMAPPED_PHASES:
        records.append({"scenario": f"{scenario_id}:baseline", **_run_one(phase, baseline)})

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

    per_activity_tokens: dict[str, list[int]] = {}
    per_activity_ratios: dict[str, list[float]] = {}
    for r in ok_records:
        activity = r["shadow"]["activity"]
        per_activity_tokens.setdefault(activity, []).append(r["shadow"]["recipe_total_tokens"])
        per_activity_ratios.setdefault(activity, []).append(r["shadow"]["recipe_to_legacy_token_ratio"])
    token_stats = {
        activity: {"min": min(vals), "max": max(vals), "avg": round(sum(vals) / len(vals), 1)}
        for activity, vals in per_activity_tokens.items()
    }
    # recipe_to_legacy_token_ratio (both sides in the same estimated-token
    # unit via recipe.py::estimate_tokens, see bundle_shadow.py) -- <1 means
    # the recipe pipeline selected a SMALLER context than the legacy bundle
    # for that activity, >1 means larger. This is the actual "does the new
    # pipeline pick a tighter or looser context" signal the CX8 evidence doc
    # flagged as missing across three prior dogfood runs.
    ratio_stats = {
        activity: {"min": min(vals), "max": max(vals), "avg": round(sum(vals) / len(vals), 3)}
        for activity, vals in per_activity_ratios.items()
    }

    return {
        "scenario_count": len(records),
        "ok_count": len(ok_records),
        "skipped_count": len(skipped_records),
        "failed_count": len(failed_records),
        "included_source_frequency": source_frequency,
        "recipe_total_tokens_by_activity": token_stats,
        "recipe_to_legacy_token_ratio_by_activity": ratio_stats,
        "failed_scenarios": [{"scenario": r["scenario"], "error": r["shadow"].get("error")} for r in failed_records],
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="optional path to also write the JSON report to")
    parser.add_argument("--summary-only", action="store_true", help="omit the full per-scenario records list")
    args = parser.parse_args()

    report = run_dogfood()
    if args.summary_only:
        report = {k: v for k, v in report.items() if k != "records"}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
