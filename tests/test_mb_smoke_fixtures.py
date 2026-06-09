"""MB-3/4/8/10 regression smoke fixtures."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "smoke_room.py"

MB_FIXTURES = (
    "evidence_gates_merged_ok",
    "evidence_ledger_stream",
    "external_handoff_attached",
    "wisdom_index_built",
)


def _load_smoke_room():
    spec = importlib.util.spec_from_file_location("smoke_room", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mb_smoke_fixtures_registered():
    smoke = _load_smoke_room()
    for name in MB_FIXTURES:
        assert name in smoke.SCENARIOS, f"missing scenario {name}"


def test_mb_smoke_fixtures_pass():
    smoke = _load_smoke_room()
    errors: list[str] = []
    for name in MB_FIXTURES:
        folder = ROOT / "sessions" / "_regression" / name
        errors.extend(smoke.validate_baseline(name, folder))
    assert not errors, "\n".join(errors)


def test_evidence_ledger_companion_has_two_rows():
    path = ROOT / "sessions" / "_regression" / "evidence_ledger_stream" / "evidence.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    assert rows[0]["phase"] == "DRY_RUN"


def test_wisdom_index_companion_has_documents():
    path = ROOT / "sessions" / "_regression" / "wisdom_index_built" / "wisdom_index.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["document_count"] >= 2
    assert len(payload["documents"]) >= 2
