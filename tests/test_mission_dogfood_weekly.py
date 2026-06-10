"""Mission dogfood weekly routine script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_weekly_module():
    path = ROOT / "scripts" / "mission_dogfood_weekly.py"
    spec = importlib.util.spec_from_file_location("mission_dogfood_weekly", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mission_dogfood_weekly_writes_artifacts(tmp_path: Path) -> None:
    mod = _load_weekly_module()
    report_dir = tmp_path / "_reports"
    payload = mod.run_weekly(
        sessions_root=tmp_path,
        report_dir=report_dir,
        days=7,
        skip_mock=False,
        include_fixtures=False,
    )

    assert payload.get("mock_session_id")
    assert payload["mock_dogfood"]["ok"] is True
    paths = payload.get("artifact_paths") or {}
    json_path = Path(paths["json"])
    md_path = Path(paths["markdown"])
    assert json_path.is_file()
    assert md_path.is_file()
    stored = json.loads(json_path.read_text(encoding="utf-8"))
    assert stored["weekly"]["period"]
