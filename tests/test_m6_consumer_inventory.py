from __future__ import annotations

import json
from pathlib import Path

from agent_lab.m6_consumer_inventory import (
    ALLOWLIST_PATH,
    REPO_ROOT,
    TARGET_FILES,
    check_references,
)


def test_scoped_legacy_references_match_checked_in_allowlist() -> None:
    unknown, stale = check_references([REPO_ROOT / path for path in TARGET_FILES])
    assert unknown == ()
    assert stale == ()


def test_allowlist_names_each_scoped_consumer() -> None:
    payload: object = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    entries = payload["entries"]
    assert isinstance(entries, list)
    paths = {entry["path"] for entry in entries if isinstance(entry, dict)}
    assert paths == set(TARGET_FILES)
    assert all(
        isinstance(entry, dict) and entry.get("owner") and entry.get("retirement_checkpoint")
        for entry in entries
    )


def test_inventory_fails_for_new_unclassified_import(tmp_path: Path) -> None:
    rogue = tmp_path / "rogue.py"
    _ = rogue.write_text("from agent_lab.run.meta import read_run_meta\n", encoding="utf-8")
    unknown, stale = check_references([rogue], root=tmp_path)
    assert {item.kind for item in unknown} == {"legacy_import", "read_run_meta"}
    assert stale == ()
