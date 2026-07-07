"""SSOT for X2 execute-lift dogfood (topic, plan, reversible marker file)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOGFood_REL = Path("docs/_dogfood/x2-lift.md")
DOGFood_PATH = ROOT / DOGFood_REL

MARKER_WRONG = "roompy에서"
MARKER_RIGHT = "room.py에서"
MARKER_LINE_HINT = "X2-lift"

TOPIC = (
    "docs/_dogfood/x2-lift.md 오타 1건(roompy→room.py) 수정 plan action을 만들어 "
    "dry-run → 승인 → merge → Oracle PASS까지 진행해 주세요."
)

PLAN_MD = f"""# X2 lift dogfood

## 지금 실행

1.
   - 무엇을: `{DOGFood_REL}` L7 세션 ID 표기 `{MARKER_WRONG}` → `{MARKER_RIGHT}` 수정
   - 어디서: `{DOGFood_REL}`
   - 검증: `grep "room\\.py" {DOGFood_REL}` 에 L7가 출력되고 `roompy` 패턴이 사라진다
   - isolation: apply
"""

VERIFY_GREP = f'grep "room\\.py" {DOGFood_REL}'


def dogfood_text() -> str:
    if not DOGFood_PATH.is_file():
        raise FileNotFoundError(f"dogfood fixture missing: {DOGFood_PATH}")
    return DOGFood_PATH.read_text(encoding="utf-8")


def has_typo(text: str | None = None) -> bool:
    body = text if text is not None else dogfood_text()
    return MARKER_WRONG in body


def has_fix(text: str | None = None) -> bool:
    body = text if text is not None else dogfood_text()
    return MARKER_WRONG not in body and MARKER_RIGHT in body


def apply_typo(*, write: bool = True) -> tuple[bool, str]:
    """Ensure fixture has the intentional typo. Returns (changed, reason)."""
    text = dogfood_text()
    if MARKER_WRONG in text:
        return False, "already_has_typo"
    if MARKER_RIGHT not in text:
        return False, "marker_missing"
    updated = text.replace(MARKER_RIGHT, MARKER_WRONG, 1)
    if write:
        DOGFood_PATH.write_text(updated, encoding="utf-8")
    return True, "reverted_to_typo"


def apply_fix(*, write: bool = True) -> tuple[bool, str]:
    """Apply the fixed slug (for mock cursor / post-run cleanup checks)."""
    text = dogfood_text()
    if MARKER_WRONG not in text:
        return False, "already_fixed"
    updated = text.replace(MARKER_WRONG, MARKER_RIGHT, 1)
    if write:
        DOGFood_PATH.write_text(updated, encoding="utf-8")
    return True, "typo_fixed"
