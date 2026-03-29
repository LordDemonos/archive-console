"""Shared Pillow raster for Archive Console tray icon - bold arrow-into-folder silhouette (original; no bundled IP)."""

from __future__ import annotations

from PIL import Image, ImageDraw

# Matte tile; folder = deep bronze (recedes); arrow = bright gold (pops at 16px).
TILE_BG = (10, 11, 13, 255)
TILE_EDGE = (54, 58, 62, 255)
GOLD_FOLDER = (142, 98, 28, 255)
GOLD_ARROW = (255, 232, 158, 255)


def draw_tray_icon(size: int) -> Image.Image:
    """
    Wide downward arrow meeting a folder opening: tab at back, solid fills only (16px-safe).

    Folder (tab + pocket) is one deep bronze shape; arrow is a much brighter gold chevron on top.
    """
    s = max(16, int(size))
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)

    r_tile = max(2, s // 8)
    edge_w = max(1, s // 16)
    dr.rounded_rectangle(
        [0, 0, s - 1, s - 1],
        radius=r_tile,
        fill=TILE_BG,
        outline=TILE_EDGE,
        width=edge_w,
    )

    inn = max(1, s // 10)
    inner = s - 2 * inn
    cx = s // 2

    # Opening: top inner edge of folder pocket (arrow tip lands just inside)
    open_y = inn + int(inner * 0.42)

    pocket_w = int(inner * 0.70)
    pocket_w = max(pocket_w, max(4, s // 2))
    pocket_x0 = cx - pocket_w // 2
    pocket_x1 = pocket_x0 + pocket_w
    pocket_x0 = max(inn, pocket_x0)
    pocket_x1 = min(s - inn - 1, pocket_x1)
    pocket_w = pocket_x1 - pocket_x0

    pocket_y0 = open_y
    pocket_y1 = s - inn - 1
    r_pocket = max(1, min(3, s // 7))

    # Rear tab (bold slab behind opening, upper-left)
    tab_w = int(inner * 0.55)
    tab_w = max(tab_w, max(3, s * 5 // 16))
    tab_h = max(2, int(inner * 0.28))
    tab_x0 = pocket_x0 - max(0, min(2, s // 10))
    tab_x1 = tab_x0 + tab_w
    tab_x1 = min(pocket_x1 + max(1, s // 14), s - inn - 1)
    tab_y1 = open_y
    tab_y0 = tab_y1 - tab_h
    tab_y0 = max(inn, tab_y0)
    r_tab = max(1, s // 12)

    dr.rounded_rectangle(
        [tab_x0, tab_y0, tab_x1, tab_y1],
        radius=r_tab,
        fill=GOLD_FOLDER,
    )
    dr.rounded_rectangle(
        [pocket_x0, pocket_y0, pocket_x1, pocket_y1],
        radius=r_pocket,
        fill=GOLD_FOLDER,
    )

    # Wide solid down-arrow: base above opening, tip inside pocket
    aw = max(int(pocket_w * 0.5), s // 4)
    base_y = inn + max(1, inner // 12)
    tip_y = open_y + max(2, s // 5)
    tip_y = min(tip_y, pocket_y1 - max(1, s // 16))

    bx0 = cx - aw
    bx1 = cx + aw
    dr.polygon(
        [(cx, tip_y), (bx0, base_y), (bx1, base_y)],
        fill=GOLD_ARROW,
    )

    return im


def draw_operator_chip(size: int) -> Image.Image:
    """Backward-compatible alias for draw_tray_icon."""
    return draw_tray_icon(size)
