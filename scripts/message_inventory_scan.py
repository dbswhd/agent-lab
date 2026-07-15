"""CM1 (08-collaboration-messaging.md) — mechanical extraction of the Room
``on_event(type, payload)`` callback inventory.

Scans every ``on_event(`` call site under ``src/agent_lab/room/`` and
``src/agent_lab/plan/workflow_state.py`` for literal event-type strings
(including indirection helpers like ``_emit``/``_emit_dispatch_events`` that
themselves call ``on_event`` with a literal). Prints the resulting set —
used both to regenerate the CM1 inventory doc and, via
``tests/test_message_inventory.py``, to catch new event types that landed
without a corresponding inventory-doc row (CM1 acceptance criteria: "미분류
on_event type ... 0").

This only covers the callback channel. SSE/chat/dispatch-ledger/MCP/gateway
are inventoried at channel granularity in the doc, not mechanically here —
see docs/redesign-2026-07/evidence/cm1-message-inventory-2026-07-16.md §0.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOM_DIR = ROOT / "src" / "agent_lab" / "room"
WORKFLOW_STATE = ROOT / "src" / "agent_lab" / "plan" / "workflow_state.py"

_ON_EVENT_LITERAL = re.compile(r'on_event\(\s*\n?\s*"([a-zA-Z0-9_.]+)"')
# _emit_dispatch_events(on_event, "dispatch_start", ...) — a literal typ passed
# to the one-level indirection helper in dispatch.py, not to on_event() itself.
_EMIT_HELPER_LITERAL = re.compile(r'_emit_dispatch_events\(\s*\n?\s*on_event,\s*\n?\s*"([a-zA-Z0-9_.]+)"')


def scan_file(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    types = {m.group(1) for m in _ON_EVENT_LITERAL.finditer(text)}
    types |= {m.group(1) for m in _EMIT_HELPER_LITERAL.finditer(text)}
    return types


def scan_callback_event_types() -> set[str]:
    types: set[str] = set()
    for path in sorted(ROOM_DIR.glob("*.py")):
        types |= scan_file(path)
    types |= scan_file(WORKFLOW_STATE)
    return types


def main() -> int:
    types = scan_callback_event_types()
    for name in sorted(types):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
