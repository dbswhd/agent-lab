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
    PLAN_MD,
    VERIFY_GREP,
    apply_fix,
    apply_typo,
    has_fix,
    has_typo,
)


def test_dogfood_fixture_can_seed_typo_for_prepare() -> None:
    assert DOGFood_PATH.is_file()
    original = DOGFood_PATH.read_text(encoding="utf-8")
    try:
        apply_typo()
        assert has_typo()
        assert not has_fix()
    finally:
        DOGFood_PATH.write_text(original, encoding="utf-8")


def test_plan_md_verify_is_evidence_row_scoped() -> None:
    """Nested cursor must not treat whole-file `grep roompy` empty as the gate."""
    assert "grep -n" in PLAN_MD
    assert "X2-lift 포함 행" in PLAN_MD
    assert MARKER_WRONG in PLAN_MD
    assert "L5·L11 설명용 roompy는 별도 행" in PLAN_MD
    assert "Evidence row에 `roompy` 패턴이 없다" not in PLAN_MD
    assert VERIFY_GREP.startswith("grep -n")


def test_prepare_typo_cycle(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "x2-lift.md"
    # Mirror real fixture: Wrong-criterion row appears BEFORE Evidence row.
    sample.write_text(
        "\n".join(
            [
                "| Wrong | `…-roompy에서-consensus-…` |",
                f"| **{MARKER_LINE_HINT}** | `…-{MARKER_WRONG}-…` |",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("x2_lift_dogfood_config.DOGFood_PATH", sample)

    changed, reason = apply_fix()
    assert changed is True
    assert reason == "typo_fixed"
    assert has_fix()
    body = sample.read_text(encoding="utf-8")
    # Wrong-criterion row must stay typo'd; only Evidence row is fixed.
    assert "| Wrong | `…-roompy에서-consensus-…` |" in body
    assert MARKER_LINE_HINT in body and "room.py에서" in body

    changed2, reason2 = apply_typo()
    assert changed2 is True
    assert reason2 == "reverted_to_typo"
    assert has_typo()

    changed3, reason3 = apply_typo()
    assert changed3 is False
    assert reason3 == "already_has_typo"
