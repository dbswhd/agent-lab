"""EN/KO message catalogs must stay in sync."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "web" / "src" / "i18n" / "messages.ts"


def _extract_keys(block: str) -> set[str]:
    keys: set[str] = set()
    for line in block.splitlines():
        m = re.match(r"^  (\w+):", line)
        if m:
            keys.add(m.group(1))
    return keys


def test_en_ko_message_keys_match():
    text = MESSAGES.read_text(encoding="utf-8")
    en_block = text.split("const EN = {", 1)[1].split("} as const;", 1)[0]
    ko_block = text.split("const KO = {", 1)[1].split("} as const;", 1)[0]
    en_keys = _extract_keys(en_block)
    ko_keys = _extract_keys(ko_block)
    assert en_keys == ko_keys, (
        f"EN-only: {sorted(en_keys - ko_keys)}; KO-only: {sorted(ko_keys - en_keys)}"
    )
