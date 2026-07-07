from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "feedback_report_snapshot.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("feedback_report_snapshot", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_snapshot_and_write(tmp_path: Path) -> None:
    mod = _load_script_module()
    payload = mod.build_snapshot(
        tmp_path,
        {"total": 3, "turn_source_counts": {"default": 1, "history": 2, "explore": 0}},
        now=datetime(2026, 7, 7, 9, 15, 30, tzinfo=UTC),
    )
    assert payload["captured_at"] == "2026-07-07T09:15:30Z"
    assert payload["root"] == str(tmp_path)
    assert payload["report"]["total"] == 3

    saved = mod.write_snapshot(tmp_path / "reports", payload)
    assert saved.is_file()
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert loaded["captured_at"] == "2026-07-07T09:15:30Z"
    assert loaded["report"]["turn_source_counts"]["history"] == 2
