"""Programmatic tray / favicon fallback — matches master language: ring, chunky bolt, smash streaks."""

from __future__ import annotations

from PIL import Image, ImageDraw

TILE_BG = (10, 11, 13, 255)
TILE_EDGE = (54, 58, 62, 255)
VOID = (0, 0, 0, 0)
RING_GOLD = (255, 210, 90, 255)
RING_INNER = (255, 245, 180, 200)
STREAK = (255, 190, 60, 200)
ARROW_OUTER = (150, 88, 16, 255)
ARROW_MID = (220, 155, 32, 255)
ARROW_INNER = (255, 230, 130, 255)
CORE = (255, 255, 255, 245)
BOLT_CORE = (220, 245, 255, 255)
BOLT_EDGE = (120, 200, 255, 255)


def draw_tray_icon(size: int) -> Image.Image:
    """
    Fallback glyph when no master PNG: one down-arrow, golden shock-ring on shaft,
    chunky electric strokes, bold downward motion lines. Safe margin inside tile.
    """
    s = max(16, int(size))
    im = Image.new("RGBA", (s, s), VOID)
    dr = ImageDraw.Draw(im)

    margin = max(1, s // 14)
    r_tile = max(2, s // 8)
    edge_w = max(1, s // 16)
    dr.rounded_rectangle(
        [0, 0, s - 1, s - 1],
        radius=r_tile,
        fill=TILE_BG,
        outline=TILE_EDGE,
        width=edge_w,
    )

    cx = s // 2
    inner_top = margin + s // 12
    inner_bot = s - margin - max(1, s // 16)
    inner_h = inner_bot - inner_top

    aw = max(s // 5, int(s * 0.37))
    base_y = inner_top + max(2, s // 20)
    tip_y = inner_bot - max(2, s // 18)
    tip_y = min(tip_y, base_y + int(inner_h * 0.82))

    # Vertical void gash (soft column behind arrow)
    g_w = max(1, s // 20)
    gy0 = base_y - s // 28
    gy1 = tip_y + s // 28
    dr.rounded_rectangle(
        [cx - g_w * 2, gy0, cx + g_w * 2, gy1],
        radius=g_w,
        fill=(40, 35, 20, 90),
    )

    # Downward motion streaks (bold, outside silhouette)
    if s >= 20:
        streak_w = max(2, s // 12)
        for i, off in enumerate((-s * 13 // 32, -s // 5, s // 5, s * 13 // 32)):
            if s < 28 and abs(off) > s // 3:
                continue
            x0 = cx + off - streak_w // 2
            y0 = base_y + s // 5 + (i % 2) * (s // 14)
            y1 = tip_y - s // 10
            dr.rounded_rectangle([x0, y0, x0 + streak_w, y1], radius=streak_w // 2, fill=STREAK)

    # Main arrow (chunky chevron)
    dr.polygon(
        [(cx, tip_y), (cx - aw, base_y), (cx + aw, base_y)],
        fill=ARROW_OUTER,
    )
    aw2 = int(aw * 0.72)
    by2 = base_y + max(1, (tip_y - base_y) // 7)
    ty2 = tip_y - max(1, s // 18)
    dr.polygon(
        [(cx, ty2), (cx - aw2, by2), (cx + aw2, by2)],
        fill=ARROW_MID,
    )
    aw3 = int(aw * 0.44)
    by3 = base_y + max(1, (tip_y - base_y) // 3)
    ty3 = tip_y - max(1, s // 12)
    dr.polygon(
        [(cx, ty3), (cx - aw3, by3), (cx + aw3, by3)],
        fill=ARROW_INNER,
    )

    # White-hot core wedge
    spine_w = max(2, s // 14)
    dr.polygon(
        [
            (cx - spine_w // 2, by3 + s // 20),
            (cx + spine_w // 2, by3 + s // 20),
            (cx, ty3 - max(1, s // 28)),
        ],
        fill=CORE,
    )

    # Golden shock-ring (horizontal ellipse on upper shaft)
    ring_cy = by2 + max(2, (ty2 - by2) // 5)
    ring_rx = min(int(aw * 1.05), s // 2 - margin - 1)
    ring_ry = max(2, s // 11)
    rw = max(2, s // 14)
    dr.ellipse(
        [cx - ring_rx, ring_cy - ring_ry, cx + ring_rx, ring_cy + ring_ry],
        outline=RING_GOLD,
        width=rw,
    )
    dr.ellipse(
        [
            cx - ring_rx + rw,
            ring_cy - ring_ry + rw // 2,
            cx + ring_rx - rw,
            ring_cy + ring_ry - rw // 2,
        ],
        outline=RING_INNER,
        width=max(1, rw // 2),
    )

    # Chunky lightning (blue-white, few segments)
    bolt_w = max(2, s // 10)
    y0 = ring_cy + ring_ry
    y1 = ty2 - s // 14
    # Left bolt
    dr.line(
        [(cx - aw - s // 8, y0), (cx - aw // 2, y0 + s // 6), (cx - aw // 3, y1)],
        fill=BOLT_EDGE,
        width=bolt_w,
    )
    dr.line(
        [(cx - aw - s // 8, y0), (cx - aw // 2, y0 + s // 6), (cx - aw // 3, y1)],
        fill=BOLT_CORE,
        width=max(1, bolt_w // 2),
    )
    # Right bolt
    dr.line(
        [(cx + aw + s // 8, y0 + s // 10), (cx + aw // 2, y0 + s // 5), (cx + aw // 4, y1)],
        fill=BOLT_EDGE,
        width=bolt_w,
    )
    dr.line(
        [(cx + aw + s // 8, y0 + s // 10), (cx + aw // 2, y0 + s // 5), (cx + aw // 4, y1)],
        fill=BOLT_CORE,
        width=max(1, bolt_w // 2),
    )

    return im


def draw_operator_chip(size: int) -> Image.Image:
    """Backward-compatible alias for draw_tray_icon."""
    return draw_tray_icon(size)
