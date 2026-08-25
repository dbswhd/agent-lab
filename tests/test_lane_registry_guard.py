"""Guard: conftest lane registries are keyed by test-module filename.

Renaming or deleting a test module silently drops it out of its lane — the suite
stays green while the test quietly moves to the fast bucket (or loses its env
setup). 2026-08-25: renaming ``test_run_schema.py`` moved 24 tests out of the
integration lane without a single failure. These asserts turn that into a red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import (
    _BRIDGE_MODULES,
    _INTEGRATION_MODULES,
    _ORCHESTRATOR_HARVEST_MODULES,
)

TESTS_DIR = Path(__file__).resolve().parent

_REGISTRIES = {
    "_INTEGRATION_MODULES": _INTEGRATION_MODULES,
    "_BRIDGE_MODULES": _BRIDGE_MODULES,
    "_ORCHESTRATOR_HARVEST_MODULES": _ORCHESTRATOR_HARVEST_MODULES,
}


@pytest.mark.parametrize("registry_name", sorted(_REGISTRIES))
def test_lane_registry_has_no_ghost_modules(registry_name: str) -> None:
    ghosts = sorted(name for name in _REGISTRIES[registry_name] if not (TESTS_DIR / f"{name}.py").exists())
    assert not ghosts, (
        f"{registry_name} names test modules that no longer exist: {ghosts}. "
        "A renamed or deleted module must be updated here, or its tests silently "
        "change lane."
    )


def test_lane_registries_do_not_overlap() -> None:
    both = sorted(_INTEGRATION_MODULES & _BRIDGE_MODULES)
    assert not both, f"modules registered as both integration and bridge: {both}"
