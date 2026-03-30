"""
Regenerate tray.ico, web favicons, and PNGs.

Primary: rescale from ``archive-console-icon-master.png`` (canonical art) with
stepwise LANCZOS + small-size contrast (see ``icon_master_derivatives.py``).

Fallback: ``tray_icon_raster.draw_tray_icon`` if the master file is missing.

Run from archive_console: python assets/build_tray_icon.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from icon_master_derivatives import load_master, render_size  # noqa: E402
from tray_icon_raster import draw_tray_icon  # noqa: E402

HERE = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MASTER = HERE / "archive-console-icon-master.png"


def _from_master() -> bool:
    if not MASTER.exists():
        return False
    print("Using master:", MASTER)
    m = load_master(MASTER)

    for side in (512, 256, 128, 64, 32):
        p = STATIC / f"app-icon-{side}.png"
        render_size(m, side).save(p, "PNG", optimize=True)
        print("Wrote", p)

    # Manifest / shortcuts (same pixels as family where sizes align)
    shutil.copy2(STATIC / "app-icon-512.png", STATIC / "icon-512.png")
    render_size(m, 192).save(STATIC / "icon-192.png", "PNG", optimize=True)
    print("Wrote", STATIC / "icon-512.png", STATIC / "icon-192.png")

    render_size(m, 32).save(STATIC / "favicon-32.png", "PNG", optimize=True)
    render_size(m, 16).save(STATIC / "favicon-16.png", "PNG", optimize=True)
    print("Wrote", STATIC / "favicon-32.png", STATIC / "favicon-16.png")

    render_size(m, 180).save(STATIC / "apple-touch-icon.png", "PNG", optimize=True)
    print("Wrote", STATIC / "apple-touch-icon.png")

    fav_frames = [render_size(m, sz) for sz in (48, 32, 16)]
    fav_ico = STATIC / "favicon.ico"
    fav_frames[0].save(
        fav_ico,
        format="ICO",
        sizes=[(f.size[0], f.size[1]) for f in fav_frames],
        append_images=fav_frames[1:],
    )
    print("Wrote", fav_ico)

    render_size(m, 256).save(HERE / "tray.png", "PNG", optimize=True)
    render_size(m, 64).save(HERE / "tray_64.png", "PNG", optimize=True)
    print("Wrote", HERE / "tray.png", HERE / "tray_64.png")

    ico_sizes = (256, 48, 32, 24, 16)
    frames = [render_size(m, sz) for sz in ico_sizes]
    ico_path = HERE / "tray.ico"
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(f.size[0], f.size[1]) for f in frames],
        append_images=frames[1:],
    )
    print("Wrote", ico_path, "sizes=", [f.size for f in frames])
    return True


def _from_vector_fallback() -> None:
    print("Master not found; using programmatic tray_icon_raster.draw_tray_icon")
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

    draw_tray_icon(16).save(STATIC / "favicon-16.png", "PNG", optimize=True)
    draw_tray_icon(32).save(STATIC / "favicon-32.png", "PNG", optimize=True)
    print("Wrote", STATIC / "favicon-16.png", STATIC / "favicon-32.png")

    draw_tray_icon(180).save(STATIC / "apple-touch-icon.png", "PNG", optimize=True)
    print("Wrote", STATIC / "apple-touch-icon.png")

    fav_frames = [draw_tray_icon(sz) for sz in (48, 32, 16)]
    fav_ico = STATIC / "favicon.ico"
    fav_frames[0].save(
        fav_ico,
        format="ICO",
        sizes=[(f.size[0], f.size[1]) for f in fav_frames],
        append_images=fav_frames[1:],
    )
    print("Wrote", fav_ico)

    draw_tray_icon(192).save(STATIC / "icon-192.png", "PNG", optimize=True)
    draw_tray_icon(512).save(STATIC / "icon-512.png", "PNG", optimize=True)
    print("Wrote", STATIC / "icon-192.png", STATIC / "icon-512.png")

    for side in (512, 256, 128, 64, 32):
        draw_tray_icon(side).save(
            STATIC / f"app-icon-{side}.png", "PNG", optimize=True
        )
        print("Wrote", STATIC / f"app-icon-{side}.png")
    shutil.copy2(STATIC / "app-icon-512.png", STATIC / "icon-512.png")
    print("Wrote", STATIC / "icon-512.png")


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    if not _from_master():
        _from_vector_fallback()


if __name__ == "__main__":
    main()
