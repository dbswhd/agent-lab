"""CM1 (08-collaboration-messaging.md) — callback event inventory stays in sync.

Guards the acceptance criterion "미분류 on_event type ... 0": every literal
event-type string reachable through on_event() in src/agent_lab/room/*.py and
plan/workflow_state.py must have a classification row in
docs/redesign-2026-07/evidence/cm1-message-inventory-2026-07-16.md §1.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from message_inventory_scan import scan_callback_event_types  # noqa: E402

DOC_PATH = ROOT / "docs/redesign-2026-07/evidence/cm1-message-inventory-2026-07-16.md"
_DOC_ROW = re.compile(r"^\| `([a-zA-Z0-9_.]+)` \| `[^|]+` \| (command|event|work_request|progress|human_decision|artifact_ref) \|")


def _doc_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in DOC_PATH.read_text(encoding="utf-8").splitlines():
        m = _DOC_ROW.match(line)
        if m:
            rows[m.group(1)] = m.group(2)
    return rows


def test_every_callback_event_type_is_classified_in_cm1_inventory() -> None:
    code_types = scan_callback_event_types()
    doc_types = set(_doc_rows())
    unclassified = code_types - doc_types
    assert not unclassified, f"on_event type(s) missing from CM1 inventory doc: {sorted(unclassified)}"


def test_cm1_inventory_has_no_stale_rows() -> None:
    code_types = scan_callback_event_types()
    doc_types = set(_doc_rows())
    stale = doc_types - code_types
    assert not stale, f"CM1 inventory row(s) no longer emitted by any on_event() call: {sorted(stale)}"


def test_cm1_inventory_kinds_are_valid() -> None:
    valid = {"command", "event", "work_request", "progress", "human_decision", "artifact_ref"}
    for event_type, kind in _doc_rows().items():
        assert kind in valid, f"{event_type}: invalid kind {kind!r}"
