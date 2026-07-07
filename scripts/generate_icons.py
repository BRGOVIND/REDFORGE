#!/usr/bin/env python3
"""Generate every branding asset from the single source image (favicon.jpg).

Center-crops the source to a square and emits the full icon set for the website,
the application, the installers, and the repo. Re-runnable and idempotent.

Usage: python scripts/generate_icons.py [path/to/favicon.jpg]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def find_source() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    candidates = sorted(
        (Path.home() / "Downloads").glob("favicon*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    raise SystemExit("favicon.jpg not found in ~/Downloads")


def load_square(src: Path) -> Image.Image:
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return im.crop((left, top, left + s, top + s))


def main() -> int:
    src = find_source()
    print(f"source: {src} ({Image.open(src).size})")
    base = load_square(src)
    bg = base.getpixel((4, 4))  # near-black corner = brand background

    def png(size: int, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        base.resize((size, size), Image.LANCZOS).save(path)

    def ico(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        base.resize((256, 256), Image.LANCZOS).save(
            path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)]
        )

    def og(path: Path) -> None:
        canvas = Image.new("RGBA", (1200, 630), bg)
        logo = base.resize((460, 460), Image.LANCZOS)
        canvas.alpha_composite(logo, ((1200 - 460) // 2, (630 - 460) // 2))
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert("RGB").save(path, quality=92)

    # Standard icon set shared by the website and the app.
    def emit_web_set(pub: Path) -> None:
        png(16, pub / "favicon-16x16.png")
        png(32, pub / "favicon-32x32.png")
        png(48, pub / "favicon-48x48.png")
        png(180, pub / "apple-touch-icon.png")
        png(192, pub / "android-chrome-192x192.png")
        png(512, pub / "android-chrome-512x512.png")
        png(150, pub / "mstile-150x150.png")
        png(512, pub / "logo-mark.png")
        ico(pub / "favicon.ico")

    emit_web_set(ROOT / "frontend" / "public")
    emit_web_set(ROOT / "website" / "public")
    og(ROOT / "website" / "public" / "og-image.png")

    # Installers (Windows .ico + Linux launcher png).
    ico(ROOT / "installers" / "windows" / "installer.ico")
    ico(ROOT / "installers" / "windows" / "desktop.ico")
    png(256, ROOT / "installers" / "linux" / "redforge.png")

    # Repo / README / GitHub branding.
    png(512, ROOT / "assets" / "logo-mark.png")

    print("done: website/public, frontend/public, installers, assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
