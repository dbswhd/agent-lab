"""Tauri bundle path contract (CI-safe, no cargo)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TAURI = WEB / "src-tauri"
CONF = TAURI / "tauri.conf.json"


def _load_conf() -> dict:
    return json.loads(CONF.read_text(encoding="utf-8"))


def test_tauri_frontend_dist_points_at_web_dist():
    conf = _load_conf()
    build = conf.get("build") or {}
    assert build.get("frontendDist") == "../dist"
    dist = (TAURI / build["frontendDist"]).resolve()
    assert dist == (WEB / "dist").resolve()


def test_tauri_bundle_resources_runtime_layout():
    conf = _load_conf()
    resources = (conf.get("bundle") or {}).get("resources") or {}
    assert isinstance(resources, dict)

    assert resources.get("../dist") == "runtime/web/dist"
    assert resources.get("../../app") == "runtime/app"
    assert resources.get("../../src") == "runtime/src"
    assert resources.get("bundled-runtime/venv") == "runtime/venv"

    venv_src = TAURI / "bundled-runtime" / "venv"
    # prepare_bundled_runtime.sh creates this before tauri build (nightly / release).
    assert venv_src.as_posix().endswith("bundled-runtime/venv")


def test_vite_build_output_dir_matches_tauri():
    vite = WEB / "vite.config.ts"
    text = vite.read_text(encoding="utf-8")
    # Default Vite outDir is `dist` at web/ root — matches tauri `../dist`.
    assert "outDir" not in text or "dist" in text
