#!/usr/bin/env python3
"""Export Agent Lab app icons via Tauri CLI (correct icns/ico for dev + release)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
MASTER_PATH = ROOT / "assets" / "icon-master.png"
ICON_DIR = WEB / "src-tauri" / "icons"
LAYER_DIR = ICON_DIR / "layers"
PUBLIC_ICON = WEB / "public" / "app-icon.png"
PUBLIC_ICON_2X = WEB / "public" / "app-icon@2x.png"
MASTER_SIZE = 1024


def ensure_master() -> None:
    if not MASTER_PATH.is_file():
        raise SystemExit(
            f"Missing master icon: {MASTER_PATH}\nPlace the approved 1024×1024 PNG at assets/icon-master.png",
        )
    img = Image.open(MASTER_PATH).convert("RGBA")
    if img.size != (MASTER_SIZE, MASTER_SIZE):
        resized = img.resize((MASTER_SIZE, MASTER_SIZE), Image.Resampling.LANCZOS)
        resized.save(MASTER_PATH, "PNG", optimize=True)


def run_tauri_icon() -> None:
    subprocess.run(
        [
            "npx",
            "tauri",
            "icon",
            str(MASTER_PATH),
            "-o",
            "src-tauri/icons",
        ],
        cwd=WEB,
        check=True,
    )


def sync_public_ui_icons() -> None:
    src_1x = ICON_DIR / "32x32.png"
    src_2x = ICON_DIR / "64x64.png"
    if not src_1x.is_file() or not src_2x.is_file():
        raise SystemExit("Tauri icon output missing 32x32.png or 64x64.png")
    shutil.copy2(src_1x, PUBLIC_ICON)
    shutil.copy2(src_2x, PUBLIC_ICON_2X)


def write_layer_readme(master: Image.Image) -> None:
    LAYER_DIR.mkdir(parents=True, exist_ok=True)
    master.save(LAYER_DIR / "master.png", "PNG", optimize=True)
    (LAYER_DIR / "README.txt").write_text(
        "Approved flat master at assets/icon-master.png (1024×1024).\nEdit that file, then run: make icons\n",
        encoding="utf-8",
    )


def main() -> None:
    ensure_master()
    master = Image.open(MASTER_PATH).convert("RGBA")
    run_tauri_icon()
    sync_public_ui_icons()
    write_layer_readme(master)
    print(f"Master: {MASTER_PATH}")
    print(f"Tauri icons → {ICON_DIR}")
    print(f"UI icons → {PUBLIC_ICON}, {PUBLIC_ICON_2X}")


if __name__ == "__main__":
    main()
