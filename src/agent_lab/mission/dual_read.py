from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agent_lab.mission.journal import JournalCorruptionError, MissionJournal
from agent_lab.mission.shadow import OrderedParityReport, build_ordered_parity_report, shadow_diff
from agent_lab.run.state import RunState

DualReadStatus = Literal["pass", "unmigrated", "drift", "invalid"]


@dataclass(frozen=True, slots=True)
class FixtureDualReadResult:
    scenario_id: str
    fixture: str
    expected_terminal_state: str
    status: DualReadStatus
    journal_present: bool
    legacy_observation_kinds: tuple[str, ...]
    observed_event_types: tuple[str, ...]
    missing_event_types: tuple[str, ...]
    unexpected_event_types: tuple[str, ...]
    unsupported_observations: tuple[str, ...]
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class FixtureDualReadReport:
    results: tuple[FixtureDualReadResult, ...]
    cutover_ready: bool


def _scenario_text(scenario: dict[str, Any], key: str, fallback: str) -> str:
    value = scenario.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _result_from_parity(
    scenario_id: str,
    fixture: str,
    expected_terminal_state: str,
    observations: tuple[Any, ...],
    parity: OrderedParityReport,
) -> FixtureDualReadResult:
    return FixtureDualReadResult(
        scenario_id,
        fixture,
        expected_terminal_state,
        "pass" if parity.parity else "drift",
        True,
        tuple(observation.kind.value for observation in observations),
        parity.observed_types,
        parity.missing_types,
        parity.unexpected_types,
        tuple(kind.value for kind in parity.unsupported_kinds),
    )


def inspect_fixture(root: Path, scenario: dict[str, Any]) -> FixtureDualReadResult:
    scenario_id = _scenario_text(scenario, "id", "unknown")
    fixture = _scenario_text(scenario, "fixture", "")
    expected = _scenario_text(scenario, "expected_terminal_state", "unknown")
    folder = root / fixture
    run_path = folder / "run.json"
    if not folder.is_dir() or not run_path.is_file():
        return FixtureDualReadResult(
            scenario_id,
            fixture,
            expected,
            "invalid",
            False,
            (),
            (),
            (),
            (),
            (),
            "legacy run.json fixture is missing",
        )
    run = RunState.from_raw(json.loads(run_path.read_text(encoding="utf-8")))
    observations = shadow_diff(RunState.empty(), run)
    journal_path = folder / ".agent-lab" / "mission-events.jsonl"
    if not journal_path.is_file():
        return FixtureDualReadResult(
            scenario_id,
            fixture,
            expected,
            "unmigrated",
            False,
            tuple(observation.kind.value for observation in observations),
            (),
            (),
            (),
            (),
            "Mission journal is not present; parity is not claimed",
        )
    try:
        stored = MissionJournal(journal_path, mission_id=folder.name).load()
    except JournalCorruptionError as exc:
        return FixtureDualReadResult(
            scenario_id,
            fixture,
            expected,
            "invalid",
            True,
            tuple(observation.kind.value for observation in observations),
            (),
            (),
            (),
            (),
            str(exc),
        )
    parity = build_ordered_parity_report(RunState.empty(), run, tuple(event.event_type for event in stored))
    return _result_from_parity(scenario_id, fixture, expected, observations, parity)


def evaluate_manifest(root: Path, manifest_path: Path) -> FixtureDualReadReport:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("scenarios"), list):
        raise ValueError("mission baseline manifest must contain scenarios")
    results = tuple(inspect_fixture(root, scenario) for scenario in raw["scenarios"] if isinstance(scenario, dict))
    return FixtureDualReadReport(results, bool(results) and all(result.status == "pass" for result in results))
