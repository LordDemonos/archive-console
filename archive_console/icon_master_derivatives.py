"""
Build icon PNGs from the canonical master raster (stepwise LANCZOS + small-size contrast).

Each output size is rescaled independently from the prepared master so detail
chains do not accumulate blur. Solid black void (#0a0b0d) under RGBA fringe.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

VOID_RGB = (10, 11, 13)


def to_square(im: Image.Image) -> Image.Image:
    w, h = im.size
    if w == h:
        return im
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def composite_on_void(im: Image.Image) -> Image.Image:
    """RGBA → RGB on void; other modes → RGB."""
    im = to_square(im)
    if im.mode == "RGBA":
        base = Image.new("RGB", im.size, VOID_RGB)
        base.paste(im, mask=im.split()[3])
        return base
    return im.convert("RGB")


def step_downscale(src: Image.Image, target: int) -> Image.Image:
    """Multi-step resize (halving) then final LANCZOS to target — preserves energy edges."""
    im = src
    w, h = im.size
    while w > target or h > target:
        nw = max(target, w // 2)
        nh = max(target, h // 2)
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        w, h = nw, nh
    if (w, h) != (target, target):
        im = im.resize((target, target), Image.Resampling.LANCZOS)
    return im


def inset_on_void(im: Image.Image, canvas: int, margin_frac: float) -> Image.Image:
    """Scale content down and center on void so rounded OS masks do not clip glow."""
    inner = max(1, int(round(canvas * (1.0 - 2.0 * margin_frac))))
    if inner >= canvas:
        return im
    scaled = im.resize((inner, inner), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (canvas, canvas), VOID_RGB)
    off = (canvas - inner) // 2
    out.paste(scaled, (off, off))
    return out


def post_for_small_pixels(im: Image.Image, side: int) -> Image.Image:
    """Punch + unsharp for 32–64 so ring / bolts / core / gold stay separated."""
    if side <= 64:
        sat = 1.04 if side >= 48 else 1.08
        im = ImageEnhance.Color(im).enhance(sat)
        c = 1.06 if side >= 48 else 1.1
        im = ImageEnhance.Contrast(im).enhance(c)
        radius = 0.32 if side >= 48 else 0.28
        pct = 110 if side >= 48 else 125
        im = im.filter(
            ImageFilter.UnsharpMask(radius=radius, percent=pct, threshold=2)
        )
    return im


def render_size(master_rgb: Image.Image, target: int) -> Image.Image:
    """
    For small targets, supersample via an intermediate >= 2x side so structure
    (ring, lightning, core) survives; then optional safe inset for <=64.
    """
    if target <= 64:
        # Intermediate ≥2× target, capped to avoid huge buffers; 512 keeps ring/bolts for 32–64 px.
        mid = max(target * 2, min(512, max(master_rgb.size)))
        blob = step_downscale(master_rgb, mid)
        out = blob.resize((target, target), Image.Resampling.LANCZOS)
        out = post_for_small_pixels(out, target)
        if target <= 64:
            out = inset_on_void(out, target, 0.055 if target <= 40 else 0.045)
        return out
    out = step_downscale(master_rgb, target)
    return post_for_small_pixels(out, target)


def load_master(path: Path) -> Image.Image:
    im = Image.open(path)
    im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
    return composite_on_void(im)


def write_family(
    master_path: Path,
    out_dir: Path,
    sizes: tuple[int, ...],
    basename: str = "app-icon",
) -> list[Path]:
    """
    Write ``{basename}-{w}.png`` for each size. Returns written paths.
    ``master_path`` must exist.
    """
    master_rgb = load_master(master_path)
    written: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for side in sizes:
        img = render_size(master_rgb, side)
        dest = out_dir / f"{basename}-{side}.png"
        img.save(dest, "PNG", optimize=True)
        written.append(dest)
    return written
