"""P1 stage 3: the typed artifact is what actually drives execution, and cannot rot.

Stage 1 wrote the artifact; nothing read it, so it was inert and free to drift out of
sync. This pins two things:

1. **Lossless round-trip** — ``PlanAction.from_dict(a.to_dict()) == a``, so the artifact
   can fully replace a re-parse rather than only supplying indices.
2. **Rot-proofing** — several writers bypass ``write_session_plan_md``
   (``room/turn_meta.py``, ``plan/advance.py``, ``session/__init__.py``, trading lane),
   so a stale on-disk artifact must never be served: the content hash forces a rebuild,
   and the healed copy is written back.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_lab.mission.loop import _action_indices_from_plan, evaluate_plan_gate
from agent_lab.plan.actions import PlanAction, parse_plan_actions
from agent_lab.plan.artifact import (
    build_plan_artifact,
    plan_action_indices_for,
    plan_actions_for,
    plan_artifact_for,
    plan_artifact_path,
    read_plan_artifact,
    refresh_plan_artifact,
)

PLAN_A = """# Title

## 지금 실행

1. Fix the typo
   - 무엇을: correct `roompy` to `room.py`
   - 어디서: `docs/x2-lift.md`
   - 검증: `grep -c 'room.py' docs/x2-lift.md`
"""

PLAN_B = """# Title

## 지금 실행

1. Rename the module
   - 무엇을: rename `old.py` to `new.py`
   - 어디서: `src/pkg/old.py`
   - 검증: `pytest tests/test_new.py`

## 실행 순서 (이후)

2. Update the docs
   - 무엇을: refresh the module table
   - 어디서: `docs/API.md`
   - 검증: `grep -c new.py docs/API.md`
"""

DEAD_PLAN = "# Title\n\n## Notes\n\nProse with no executable section at all.\n"


# --- lossless round-trip ----------------------------------------------------


def test_plan_action_round_trips_through_dict() -> None:
    for plan in (PLAN_A, PLAN_B, DEAD_PLAN):
        for action in parse_plan_actions(plan):
            assert PlanAction.from_dict(action.to_dict()) == action


def test_round_trip_recomputes_derived_paths_rather_than_trusting_them() -> None:
    """A tampered artifact must not smuggle in paths the plan text never mentions."""
    action = next(a for a in parse_plan_actions(PLAN_A) if a.executable)
    row = action.to_dict()
    row["expected_paths"] = ["/etc/passwd"]
    assert PlanAction.from_dict(row).expected_paths() == action.expected_paths()
    assert "/etc/passwd" not in PlanAction.from_dict(row).expected_paths()


def test_artifact_actions_reconstruct_to_the_parsed_actions() -> None:
    artifact = build_plan_artifact(PLAN_B)
    rebuilt = [PlanAction.from_dict(row) for row in artifact.actions]
    assert rebuilt == list(parse_plan_actions(PLAN_B))


# --- rot-proofing -----------------------------------------------------------


def test_stale_artifact_is_never_served(tmp_path: Path) -> None:
    """A plan written by a path that bypasses the seam must not serve old actions."""
    refresh_plan_artifact(tmp_path, PLAN_A)
    # Simulate room/turn_meta.py writing plan.md directly.
    actions = plan_actions_for(tmp_path, PLAN_B)
    assert [a["what"] for a in actions] == [
        "rename `old.py` to `new.py`",
        "refresh the module table",
    ]


def test_stale_artifact_is_healed_on_disk(tmp_path: Path) -> None:
    refresh_plan_artifact(tmp_path, PLAN_A)
    plan_artifact_for(tmp_path, PLAN_B)
    healed = read_plan_artifact(tmp_path)
    assert healed is not None
    assert healed.executable_count == 2, "the on-disk copy must be rewritten, not just the return value"


def test_persist_false_leaves_disk_untouched(tmp_path: Path) -> None:
    refresh_plan_artifact(tmp_path, PLAN_A)
    plan_artifact_for(tmp_path, PLAN_B, persist=False)
    stored = read_plan_artifact(tmp_path)
    assert stored is not None
    assert stored.executable_count == 1


def test_corrupt_artifact_self_heals(tmp_path: Path) -> None:
    path = plan_artifact_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{corrupt", encoding="utf-8")
    assert plan_action_indices_for(tmp_path, PLAN_A) == [1]
    assert read_plan_artifact(tmp_path) is not None


def test_read_path_matches_direct_parse(tmp_path: Path) -> None:
    """The artifact read path must agree with the parser it replaces."""
    for plan in (PLAN_A, PLAN_B, DEAD_PLAN):
        direct = [a.index for a in parse_plan_actions(plan) if a.executable]
        assert plan_action_indices_for(tmp_path, plan) == direct


# --- execution-critical sites now read the artifact -------------------------


def test_execute_queue_indices_use_the_artifact(tmp_path: Path) -> None:
    refresh_plan_artifact(tmp_path, PLAN_B)
    assert _action_indices_from_plan(PLAN_B, tmp_path) == [1, 2]


def test_execute_queue_indices_without_folder_still_work() -> None:
    """Folder-less callers keep the direct parse — no signature break."""
    assert _action_indices_from_plan(PLAN_B) == [1, 2]


def test_plan_gate_agrees_with_and_without_a_folder(tmp_path: Path) -> None:
    """Routing the gate through the artifact must not change its verdict."""
    for plan in (PLAN_A, PLAN_B, DEAD_PLAN):
        with_folder = evaluate_plan_gate(plan, run={}, session_folder=tmp_path)
        without = evaluate_plan_gate(plan)
        assert with_folder["status"] == without["status"]
        assert with_folder.get("reason") == without.get("reason")
        assert with_folder.get("action_count") == without.get("action_count")


def test_plan_gate_uses_fresh_actions_after_plan_change(tmp_path: Path) -> None:
    refresh_plan_artifact(tmp_path, DEAD_PLAN)
    result = evaluate_plan_gate(PLAN_B, run={}, session_folder=tmp_path)
    assert result["status"] == "ok"
    assert result["action_count"] == 2


# --- drift baseline ---------------------------------------------------------


def test_drift_baseline_uses_the_artifact(tmp_path: Path) -> None:
    from agent_lab.drift_audit import snapshot_drift_baseline

    (tmp_path / "run.json").write_text("{}", encoding="utf-8")
    snapshot_drift_baseline(tmp_path, PLAN_B, 1)

    run = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    baseline = run["drift_baseline"]
    assert [a["index"] for a in baseline["actions"]] == [1, 2]
    assert all(a["what"] for a in baseline["actions"])


# --- no plan writer is forgotten -------------------------------------------


def test_plan_md_writers_are_known(tmp_path: Path) -> None:
    """Any new plan.md writer must be reviewed for artifact staleness.

    Not a ban — ``plan_artifact_for`` heals stale copies on read. This is a tripwire so
    a new writer is a deliberate decision rather than a silent source of drift.
    """
    import subprocess

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["grep", "-rln", r'plan_path.write_text\|/ "plan.md").write_text', "src/agent_lab"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    known = {
        "src/agent_lab/plan/paths.py",  # the seam itself
        "src/agent_lab/plan/advance.py",
        "src/agent_lab/room/turn_meta.py",
        "src/agent_lab/session/__init__.py",
        "src/agent_lab/quant/utility_validation.py",
        "src/agent_lab/trading_mission/v1_ops.py",
        "src/agent_lab/trading_mission/offline_lane.py",
        "src/agent_lab/trading_mission/mock_artifacts.py",
    }
    found = {line.strip() for line in out.stdout.splitlines() if line.strip()}
    assert found <= known, (
        f"new plan.md writer(s) not reviewed for typed-artifact staleness: {sorted(found - known)}. "
        "Either route the write through plan/paths.write_session_plan_md or add it here."
    )
