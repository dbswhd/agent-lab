#!/usr/bin/env python3
"""Export Agent Lab app icons from the approved master artwork (tri-arc C mark)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "assets" / "icon-master.png"
ICON_DIR = ROOT / "web" / "src-tauri" / "icons"
LAYER_DIR = ICON_DIR / "layers"
PUBLIC_ICON = ROOT / "web" / "public" / "app-icon.png"
MASTER_SIZE = 1024


def load_master() -> Image.Image:
    if not MASTER_PATH.is_file():
        raise SystemExit(
            f"Missing master icon: {MASTER_PATH}\n"
            "Place the approved 1024×1024 PNG at assets/icon-master.png",
        )
    img = Image.open(MASTER_PATH).convert("RGBA")
    if img.size != (MASTER_SIZE, MASTER_SIZE):
        img = img.resize((MASTER_SIZE, MASTER_SIZE), Image.Resampling.LANCZOS)
    return img


def write_png(path: Path, img: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(path, "PNG", optimize=True)


def build_iconset(icon: Image.Image, iconset: Path) -> None:
    iconset.mkdir(parents=True, exist_ok=True)
    for name, px in [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]:
        write_png(iconset / name, icon.resize((px, px), Image.Resampling.LANCZOS))


def main() -> None:
    master = load_master()

    ICON_DIR.mkdir(parents=True, exist_ok=True)
    write_png(ICON_DIR / "icon.png", master)
    write_png(ICON_DIR / "32x32.png", master.resize((32, 32), Image.Resampling.LANCZOS))
    write_png(ICON_DIR / "128x128.png", master.resize((128, 128), Image.Resampling.LANCZOS))
    write_png(
        ICON_DIR / "128x128@2x.png",
        master.resize((256, 256), Image.Resampling.LANCZOS),
    )
    write_png(PUBLIC_ICON, master.resize((192, 192), Image.Resampling.LANCZOS))

    LAYER_DIR.mkdir(parents=True, exist_ok=True)
    write_png(LAYER_DIR / "master.png", master)
    (LAYER_DIR / "README.txt").write_text(
        "Approved flat master at assets/icon-master.png (1024×1024).\n"
        "Edit that file, then run: make icons\n",
        encoding="utf-8",
    )

    for sq, px in [
        ("Square30x30Logo.png", 30),
        ("Square44x44Logo.png", 44),
        ("Square71x71Logo.png", 71),
        ("Square89x89Logo.png", 89),
        ("Square107x107Logo.png", 107),
        ("Square142x142Logo.png", 142),
        ("Square150x150Logo.png", 150),
        ("Square284x284Logo.png", 284),
        ("Square310x310Logo.png", 310),
        ("StoreLogo.png", 50),
    ]:
        write_png(ICON_DIR / sq, master.resize((px, px), Image.Resampling.LANCZOS))

    iconset = ICON_DIR / "AppIcon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    build_iconset(master, iconset)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(ICON_DIR / "icon.icns")],
        check=True,
    )
    shutil.rmtree(iconset)
    master.save(
        ICON_DIR / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Master: {MASTER_PATH}")
    print(f"Wrote icons → {ICON_DIR}")


if __name__ == "__main__":
    main()
