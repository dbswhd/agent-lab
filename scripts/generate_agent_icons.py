#!/usr/bin/env python3
"""Refresh agent chat icons from macOS .app bundles (filled square)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "icons"
APPS = {
    "cursor": Path("/Applications/Cursor.app/Contents/Resources/Cursor.icns"),
    "codex": Path("/Applications/Codex.app/Contents/Resources/icon.icns"),
    "claude": Path("/Applications/Claude.app/Contents/Resources/electron.icns"),
}
SIZE = 128


def load_icns(path: Path) -> Image.Image:
    return Image.open(path).convert("RGBA")


def fill_square(img: Image.Image, size: int) -> Image.Image:
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    scale = (size * 0.82) / max(w, h)
    nw, nh = int(w * scale), int(h * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - nw) // 2, (size - nh) // 2), img)
    return canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, path in APPS.items():
        if not path.is_file():
            print(f"skip {name}: {path} missing")
            continue
        out = fill_square(load_icns(path), SIZE)
        out.save(OUT / f"{name}.png", "PNG", optimize=True)
        print(f"wrote {name}.png")


if __name__ == "__main__":
    main()
