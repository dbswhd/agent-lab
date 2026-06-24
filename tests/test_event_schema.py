"""P5 typed event schema (AGENT_LAB_EVENT_MEMORY, default off).

Covers AC1-AC7 + AC15 directional no-importer OFF-parity scan (event_schema MAY
import room_live_log; room_live_log MUST NOT import the new modules; no other consumer).
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_lab import event_schema as es
from agent_lab.room_live_log import LIVE_EVENT_TYPES

_SRC = Path(__file__).resolve().parent.parent / "src" / "agent_lab"


def test_ac1_event_types_proper_superset():
    assert set(LIVE_EVENT_TYPES) <= set(es.EVENT_TYPES)
    # extras present
    assert {"node_status", "run_patch"} <= set(es.EVENT_TYPES)


def test_ac2_make_event_stamps_ts():
    ev = es.make_event("agent_start", agent="codex")
    assert ev["type"] == "agent_start"
    assert ev["agent"] == "codex"
    assert isinstance(ev["ts"], str) and ev["ts"]


def test_ac3_explicit_ts_reproducible():
    ev = es.make_event("tool_done", ts="2026-01-01T00:00:00+00:00", tool="x")
    assert ev["ts"] == "2026-01-01T00:00:00+00:00"
    # same args => same output
    ev2 = es.make_event("tool_done", ts="2026-01-01T00:00:00+00:00", tool="x")
    assert ev == ev2


def test_ac4_unknown_type_raises():
    try:
        es.make_event("not_a_real_type")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown type")


def test_ac5_validate_valid():
    ev = es.make_event("agent_done")
    ok, errors = es.validate_event(ev)
    assert ok is True
    assert errors == []


def test_ac6_validate_surfaces_each_defect():
    # unknown_type
    ok, errors = es.validate_event({"type": "bogus", "ts": "t"})
    assert ok is False and "unknown_type" in errors
    # missing_ts
    ok, errors = es.validate_event({"type": "agent_start"})
    assert ok is False and "missing_ts" in errors
    # payload_not_dict
    ok, errors = es.validate_event(["not", "a", "dict"])
    assert ok is False and errors == ["payload_not_dict"]
    # ok == (errors == [])
    ok2, errors2 = es.validate_event({"type": "agent_start", "ts": "t"})
    assert ok2 == (errors2 == [])


def test_ac7_schema_pure_deterministic():
    a = es.validate_event({"type": "agent_start", "ts": "t"})
    b = es.validate_event({"type": "agent_start", "ts": "t"})
    assert a == b


# --- AC15 directional OFF-parity contract -----------------------------------

_IMPORT_RE = re.compile(r"^\s*(?:from\s+agent_lab\.(\w+)\s+import|import\s+agent_lab\.(\w+))", re.M)


def _imported_modules(py: Path) -> set[str]:
    text = py.read_text(encoding="utf-8")
    mods: set[str] = set()
    for m in _IMPORT_RE.finditer(text):
        mods.add(m.group(1) or m.group(2))
    return mods


def test_ac15_directional_no_importer_contract():
    new_modules = {"event_schema", "memory_store"}
    # (iii) no src module other than the new modules imports either new module
    offenders = []
    for py in _SRC.glob("*.py"):
        if py.stem in new_modules:
            continue
        if _imported_modules(py) & new_modules:
            offenders.append(py.name)
    assert offenders == [], f"unexpected importers of new modules: {offenders}"

    # (ii) room_live_log must NOT import either new module (reverse edge)
    rll = _imported_modules(_SRC / "room_live_log.py")
    assert not (rll & new_modules), f"room_live_log imports new modules: {rll & new_modules}"

    # (i) event_schema MAY import room_live_log (the one allowed edge) — and does
    assert "room_live_log" in _imported_modules(_SRC / "event_schema.py")


def test_enabled_helper(monkeypatch):
    # default ON: absent/empty => enabled; opt-out via =0
    monkeypatch.delenv("AGENT_LAB_EVENT_MEMORY", raising=False)
    assert es.event_memory_enabled() is True
    monkeypatch.setenv("AGENT_LAB_EVENT_MEMORY", "0")
    assert es.event_memory_enabled() is False
    monkeypatch.setenv("AGENT_LAB_EVENT_MEMORY", "1")
    assert es.event_memory_enabled() is True


def test_event_validation_enabled_default_off(monkeypatch):
    # behavior-change gate stays default OFF
    monkeypatch.delenv("AGENT_LAB_EVENT_VALIDATE", raising=False)
    assert es.event_validation_enabled() is False
    monkeypatch.setenv("AGENT_LAB_EVENT_VALIDATE", "1")
    assert es.event_validation_enabled() is True
