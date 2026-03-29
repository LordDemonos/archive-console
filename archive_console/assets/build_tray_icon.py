"""
Regenerate tray.ico and source PNGs (arrow-into-folder silhouette).

Run from archive_console: python assets/build_tray_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tray_icon_raster import draw_tray_icon  # noqa: E402

HERE = Path(__file__).resolve().parent


def main() -> None:
    # ICO: 16, 24, 32, 48 per spec + 256 for pystray/HiDPI rescale
    ico_sizes = (256, 48, 32, 24, 16)

    img256 = draw_tray_icon(256)
    img256.save(HERE / "tray.png", "PNG", optimize=True)
    print("Wrote", HERE / "tray.png")

    img64 = draw_tray_icon(64)
    img64.save(HERE / "tray_64.png", "PNG", optimize=True)
    print("Wrote", HERE / "tray_64.png")

    frames = [draw_tray_icon(sz) for sz in ico_sizes]
    ico_path = HERE / "tray.ico"
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(f.size[0], f.size[1]) for f in frames],
        append_images=frames[1:],
    )
    print("Wrote", ico_path, "sizes=", [f.size for f in frames])


if __name__ == "__main__":
    main()
