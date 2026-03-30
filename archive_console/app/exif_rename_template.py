"""
Filename templates from ExifTool JSON (-j -n) tags.

v1 tokens (see ARCHIVE_CONSOLE.md Rename section):
  {Stem}              — current pipeline stem (after prior steps; starts as filename stem)
  {Model}             — camera model (several ExifTool key aliases)
  {LensModel}         — lens
  {ImageSize}         — e.g. 4032x3024
  {DateTimeOriginal:FORMAT} — first available date in fallback chain, strftime FORMAT
  {CreateDate:FORMAT} — same fallback chain (alias for date-from-metadata)

Date fallback order (first non-empty parseable wins):
  EXIF:DateTimeOriginal, EXIF:CreateDate, QuickTime:CreateDate, Keys:CreateDate,
  CreateDate, MediaCreateDate, EXIF:ModifyDate, FileModifyDate
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_TOKEN = re.compile(r"\{([^{}]+)\}")

# Keys tried in order for date tokens (DateTimeOriginal / CreateDate with format).
_DATE_FALLBACK_KEYS: tuple[str, ...] = (
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "QuickTime:CreateDate",
    "Keys:CreateDate",
    "CreateDate",
    "MediaCreateDate",
    "EXIF:ModifyDate",
    "FileModifyDate",
)

_MODEL_KEYS: tuple[str, ...] = (
    "Model",
    "EXIF:Model",
    "Canon:Model",
    "Sony:Model",
    "Nikon:Model",
)

_LENS_KEYS: tuple[str, ...] = (
    "LensModel",
    "EXIF:LensModel",
    "Canon:LensModel",
)

_IMAGE_SIZE_KEYS: tuple[str, ...] = (
    "ImageSize",
    "EXIF:ImageSize",
    "Composite:ImageSize",
)


def _lookup(tags: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = tags.get(k)
        if v is None or v == "":
            continue
        s = str(v).strip()
        if s and s.lower() not in ("unknown", "n/a", "na"):
            return s
    return ""


def parse_exif_datetime(val: str) -> datetime | None:
    """Parse common ExifTool date strings."""
    s = (val or "").strip()
    if not s:
        return None
    if len(s) >= 19:
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s[:19], fmt)
            except ValueError:
                continue
    if len(s) >= 10:
        for fmt in ("%Y:%m:%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:10], fmt)
            except ValueError:
                continue
    return None


def first_date_from_tags(tags: dict[str, Any]) -> datetime | None:
    for k in _DATE_FALLBACK_KEYS:
        raw = _lookup(tags, (k,))
        if not raw:
            continue
        dt = parse_exif_datetime(raw)
        if dt:
            return dt
    return None


def normalize_image_size(s: str) -> str:
    t = s.replace("x", " ").replace("X", " ")
    parts = t.split()
    if len(parts) >= 2:
        return f"{parts[0]}x{parts[1]}"
    return s.replace(" ", "x") if " " in s else s


def _split_token(spec: str) -> tuple[str, str | None]:
    spec = spec.strip()
    if ":" in spec:
        name, _, fmt = spec.partition(":")
        return name.strip(), fmt.strip() or None
    return spec, None


def render_exif_template(
    template: str,
    tags: dict[str, Any],
    *,
    pipeline_stem: str,
    used_tags: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    """
    Replace {Token} and {Token:fmt} in template. {Stem} uses pipeline_stem.
    Returns (rendered_string, warnings).
    """
    warnings: list[str] = []
    if used_tags is None:
        used_tags = {}

    def repl(m: re.Match[str]) -> str:
        spec = m.group(1)
        name, fmt = _split_token(spec)

        if name == "Stem":
            used_tags["Stem"] = pipeline_stem
            return pipeline_stem

        if name in ("DateTimeOriginal", "CreateDate", "MediaCreateDate"):
            dt = first_date_from_tags(tags)
            if dt is None:
                warnings.append(f"no date for {{{spec}}}")
                return ""
            if not fmt:
                fmt = "%Y%m%d"
            try:
                out = dt.strftime(fmt)
                used_tags[name] = out
                return out
            except ValueError:
                warnings.append(f"bad strftime format in {{{spec}}}")
                return ""

        if name == "Model":
            v = _lookup(tags, _MODEL_KEYS)
            if v:
                used_tags["Model"] = v
            else:
                warnings.append("missing Model")
            return v

        if name == "LensModel":
            v = _lookup(tags, _LENS_KEYS)
            if v:
                used_tags["LensModel"] = v
            else:
                warnings.append("missing LensModel")
            return v

        if name == "ImageSize":
            v = _lookup(tags, _IMAGE_SIZE_KEYS)
            if v:
                v = normalize_image_size(v)
                used_tags["ImageSize"] = v
            else:
                warnings.append("missing ImageSize")
            return v

        # Generic: try exact ExifTool key
        v = tags.get(name)
        if v is None or str(v).strip() == "":
            warnings.append(f"unknown or empty tag {name!r}")
            return ""
        s = str(v).strip()
        if fmt:
            dt = parse_exif_datetime(s)
            if dt:
                try:
                    out = dt.strftime(fmt)
                    used_tags[name] = out
                    return out
                except ValueError:
                    warnings.append(f"bad strftime for {name!r}")
                    return ""
        used_tags[name] = s
        return s

    out = _TOKEN.sub(repl, template)
    return out, warnings


def forbid_path_seps(s: str) -> str:
    return s.replace("/", "_").replace("\\", "_").replace("..", "__")
