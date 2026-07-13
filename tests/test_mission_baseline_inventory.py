from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, TypedDict

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
MANIFEST: Final[Path] = ROOT / "tests" / "fixtures" / "mission-baseline.json"
INVENTORY_DOC: Final[Path] = ROOT / "docs" / "redesign-2026-07" / "00-wave0-mission-inventory.md"
REQUIRED_SCENARIOS: Final[frozenset[str]] = frozenset(
    {
        "plan_reject_revisit",
        "execute_success_merge_oracle_pass",
        "oracle_fail_repair",
        "human_inbox_pause_resume",
        "daemon_crash_recovery",
    }
)
CLASSIFICATIONS: Final[frozenset[str]] = frozenset({"map", "projection-only", "retire"})


class ScenarioRecord(TypedDict):
    id: str
    fixture: str
    expected_terminal_state: str
    expected_gate: str
    writers: list[str]
    classification: str


class ManifestRecord(TypedDict):
    version: int
    inventory_document: str
    scenarios: list[ScenarioRecord]


def _load_manifest() -> ManifestRecord:
    raw: Any = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError("manifest root must be an object")
    parsed: ManifestRecord = {
        "version": raw["version"],
        "inventory_document": raw["inventory_document"],
        "scenarios": raw["scenarios"],
    }
    return parsed


def test_wave0_manifest_has_all_representative_scenarios() -> None:
    assert MANIFEST.is_file()
    manifest = _load_manifest()
    names = {row["id"] for row in manifest["scenarios"]}
    assert names == REQUIRED_SCENARIOS


def test_wave0_manifest_points_to_existing_fixtures_and_classifies_writers() -> None:
    manifest = _load_manifest()
    for row in manifest["scenarios"]:
        fixture = row.get("fixture")
        writers = row.get("writers")
        classification = row.get("classification")
        assert isinstance(fixture, str)
        assert (ROOT / fixture).exists(), fixture
        assert writers
        assert all(writer for writer in writers)
        assert classification in CLASSIFICATIONS


def test_wave0_inventory_doc_is_linked_from_manifest() -> None:
    manifest = _load_manifest()
    assert manifest["inventory_document"] == "docs/redesign-2026-07/00-wave0-mission-inventory.md"
    text = INVENTORY_DOC.read_text(encoding="utf-8")
    for scenario_id in REQUIRED_SCENARIOS:
        assert scenario_id in text
