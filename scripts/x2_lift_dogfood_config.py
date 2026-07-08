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
   - 무엇을: `{DOGFood_REL}` L17 Evidence row 세션 ID `{MARKER_WRONG}` → `{MARKER_RIGHT}` 수정
   - 어디서: `{DOGFood_REL}`
   - 검증: `grep "room\\.py" {DOGFood_REL}` 에 L17이 출력되고, Evidence row에 `roompy` 패턴이 없다
   - isolation: apply
"""

VERIFY_GREP = f'grep "room\\.py" {DOGFood_REL}'


def dogfood_text() -> str:
    if not DOGFood_PATH.is_file():
        raise FileNotFoundError(f"dogfood fixture missing: {DOGFood_PATH}")
    return DOGFood_PATH.read_text(encoding="utf-8")


def _evidence_line(body: str) -> str | None:
    for line in body.splitlines():
        if MARKER_LINE_HINT in line:
            return line
    return None


def has_typo(text: str | None = None) -> bool:
    body = text if text is not None else dogfood_text()
    line = _evidence_line(body)
    return bool(line and MARKER_WRONG in line)


def has_fix(text: str | None = None) -> bool:
    body = text if text is not None else dogfood_text()
    line = _evidence_line(body)
    return bool(line and MARKER_RIGHT in line and MARKER_WRONG not in line)


def apply_typo(*, write: bool = True) -> tuple[bool, str]:
    """Ensure Evidence row has the intentional typo. Returns (changed, reason)."""
    text = dogfood_text()
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    for line in lines:
        if MARKER_LINE_HINT in line and MARKER_RIGHT in line:
            line = line.replace(MARKER_RIGHT, MARKER_WRONG, 1)
            changed = True
        out.append(line)
    if not changed:
        if has_typo(text):
            return False, "already_has_typo"
        return False, "marker_missing"
    if write:
        DOGFood_PATH.write_text("".join(out), encoding="utf-8")
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
