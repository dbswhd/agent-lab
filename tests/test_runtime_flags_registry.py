"""F10 — runtime_flags registry drift guard (measured code refs vs FLAG_REGISTRY)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent_lab.runtime_flags import FLAG_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agent_lab"
ALLOWLIST_PATH = ROOT / "tests" / "fixtures" / "runtime-flags-registry-allowlist.json"
_FLAG_RE = re.compile(r"AGENT_LAB_[A-Z0-9_]+")


def _load_allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def scan_agent_lab_flags() -> set[str]:
    """Measured AGENT_LAB_* env names referenced in src/agent_lab Python sources."""
    found: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        found.update(_FLAG_RE.findall(path.read_text(encoding="utf-8")))
    return found


def registry_flag_names() -> set[str]:
    return {row.name for row in FLAG_REGISTRY}


def test_f10_scanned_and_registry_counts_match_baseline() -> None:
    """Ratchet measured/registry sizes — update allowlist fixture when intentionally changed."""
    baseline = _load_allowlist()
    scanned = scan_agent_lab_flags()
    registry = registry_flag_names()
    assert len(scanned) == baseline["scanned_count"], (
        f"scanned count drift: got {len(scanned)}, baseline {baseline['scanned_count']}"
    )
    assert len(registry) == baseline["registry_count"], (
        f"registry count drift: got {len(registry)}, baseline {baseline['registry_count']}"
    )


def test_f10_flag_registry_symmetric_difference_zero_after_allowlist() -> None:
    """Code↔registry symmetric difference must be empty once allowlists are applied."""
    baseline = _load_allowlist()
    scanned = scan_agent_lab_flags()
    registry = registry_flag_names()

    code_allow = set(baseline["code_not_registry_allowlist"])
    registry_allow = set(baseline["registry_not_code_allowlist"])

    code_only = scanned - registry
    registry_only = registry - scanned

    unexpected_code = sorted(code_only - code_allow)
    unexpected_registry = sorted(registry_only - registry_allow)

    assert unexpected_code == [], (
        "AGENT_LAB_* in src/agent_lab but not FLAG_REGISTRY (register or allowlist): " + ", ".join(unexpected_code)
    )
    assert unexpected_registry == [], (
        "FLAG_REGISTRY entries absent from src/agent_lab scan (fix name or allowlist): "
        + ", ".join(unexpected_registry)
    )

    stale_code_allow = sorted(code_allow - code_only)
    stale_registry_allow = sorted(registry_allow - registry_only)

    assert stale_code_allow == [], "Remove from code_not_registry_allowlist (now registered): " + ", ".join(
        stale_code_allow
    )
    assert stale_registry_allow == [], "Remove from registry_not_code_allowlist (now referenced in code): " + ", ".join(
        stale_registry_allow
    )

    assert code_only == code_allow
    assert registry_only == registry_allow


def test_f10_allowlist_covers_current_drift_exactly() -> None:
    """Guard allowlist size — grows only via explicit fixture update."""
    baseline = _load_allowlist()
    scanned = scan_agent_lab_flags()
    registry = registry_flag_names()
    assert len(scanned - registry) == len(baseline["code_not_registry_allowlist"])
    assert len(registry - scanned) == len(baseline["registry_not_code_allowlist"])
    trading = set(baseline.get("trading_lane_internal") or [])
    internal_trading = {name for name in trading if name in registry}
    assert internal_trading == trading, f"trading_lane_internal not in registry: {sorted(trading - internal_trading)}"
