"""X2 dogfood fixture — reversible typo prepare cycle."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from x2_lift_dogfood_config import (  # noqa: E402
    DOGFood_PATH,
    MARKER_LINE_HINT,
    MARKER_WRONG,
    apply_fix,
    apply_typo,
    has_fix,
    has_typo,
)


def test_dogfood_fixture_has_typo_by_default() -> None:
    assert DOGFood_PATH.is_file()
    assert has_typo()
    assert not has_fix()


def test_prepare_typo_cycle(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "x2-lift.md"
    sample.write_text(f"| **{MARKER_LINE_HINT}** | `…-{MARKER_WRONG}-…` |\n", encoding="utf-8")
    monkeypatch.setattr("x2_lift_dogfood_config.DOGFood_PATH", sample)

    changed, reason = apply_fix()
    assert changed is True
    assert reason == "typo_fixed"
    assert has_fix()

    changed2, reason2 = apply_typo()
    assert changed2 is True
    assert reason2 == "reverted_to_typo"
    assert has_typo()

    changed3, reason3 = apply_typo()
    assert changed3 is False
    assert reason3 == "already_has_typo"
