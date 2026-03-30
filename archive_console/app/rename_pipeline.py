"""
Rename pipeline: preview/apply with pluggable operations.

Operations compose in order: ExifTool filename template ({Stem}, {Model}, dates, …)
and/or DeepL stem translation. Final basename = fold_steps(original_stem) + extension;
Path.rename after preview token (see apply_rename_preview). Future: regex, counters —
append new step kinds without changing the preview_id → apply contract.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .deepl_translate import (
    DeepLClientError,
    effective_deepl_api_key,
    resolve_deepl_base_url,
    translate_texts,
)
from .exif_rename_template import forbid_path_seps, render_exif_template
from .exiftool_read import resolve_exiftool_bin, run_exiftool_json
from .paths import PathNotAllowedError, assert_allowed_path, normalize_rel

logger = logging.getLogger(__name__)

PREVIEW_TTL_SEC = 900
MAX_FILES_DEFAULT = 50
MAX_FILES_HARD = 200

_WIN_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DATE_PREFIX = re.compile(r"^(\d{8})(.+)$")
_YT_STEM_SUFFIX = re.compile(r"^(.+)-([A-Za-z0-9_-]{11})$")
_BRACKET_SEG = re.compile(r"【[^】]*】")

OperationKind = Literal["translate_stem_deepl", "apply_exif_template"]


class RenameTranslateDeepLOptions(BaseModel):
    """Options for translate_stem_deepl (v1)."""

    whole_basename: bool = False
    preserve_youtube_id: bool = True
    preserve_brackets: bool = True


class RenamePreviewOptions(BaseModel):
    """Rename preview body `options` (flat JSON for backward compatibility)."""

    whole_basename: bool = False
    preserve_youtube_id: bool = True
    preserve_brackets: bool = True
    use_deepl: bool = True
    use_exif: bool = False
    pipeline_order: Literal["exif_then_deepl", "deepl_then_exif"] = "exif_then_deepl"
    exif_template: str = ""
    exif_missing_policy: Literal["skip", "keep_basename"] = "keep_basename"

    def deepl_sub(self) -> RenameTranslateDeepLOptions:
        return RenameTranslateDeepLOptions(
            whole_basename=self.whole_basename,
            preserve_youtube_id=self.preserve_youtube_id,
            preserve_brackets=self.preserve_brackets,
        )


class RenamePlan(BaseModel):
    """Ordered operations (documentation / future API); runtime uses RenamePreviewOptions."""

    operations: list[tuple[OperationKind, dict[str, Any]]] = Field(
        default_factory=list
    )


def split_basename(name: str) -> tuple[str, str]:
    """Stem and extension (extension includes leading dot, or '')."""
    if not name or name in (".", ".."):
        return name, ""
    if name.startswith(".") and name.count(".") == 1:
        return name, ""
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        return stem, "." + ext
    return name, ""


def shield_brackets(stem: str) -> tuple[str, list[str]]:
    """Replace each 【…】 with <<BRn>>; return (shielded, originals in order)."""
    parts: list[str] = []

    def repl(m: re.Match[str]) -> str:
        parts.append(m.group(0))
        return f"<<BR{len(parts) - 1}>>"

    return _BRACKET_SEG.sub(repl, stem), parts


def unshield_brackets(translated: str, originals: list[str]) -> str:
    out = translated
    for i, frag in enumerate(originals):
        out = out.replace(f"<<BR{i}>>", frag)
    return out


def prepare_deepl_input(
    stem: str,
    *,
    whole_basename: bool,
    preserve_youtube_id: bool,
    preserve_brackets: bool,
) -> tuple[str, str, str, list[str]]:
    """
    Build (prefix, deepl_text, suffix, bracket_originals).
    Final stem = prefix + unshield(deepl_translated, bracket_originals) + suffix.
    """
    date_prefix = ""
    rest = stem
    if not whole_basename:
        m = _DATE_PREFIX.match(stem)
        if m:
            date_prefix, rest = m.group(1), m.group(2)
    yt_suffix = ""
    mid = rest
    if preserve_youtube_id and not whole_basename:
        ym = _YT_STEM_SUFFIX.match(rest)
        if ym:
            mid, yt_suffix = ym.group(1), "-" + ym.group(2)
    bracket_parts: list[str] = []
    to_translate = mid
    if preserve_brackets:
        to_translate, bracket_parts = shield_brackets(mid)
    return date_prefix, to_translate, yt_suffix, bracket_parts


def sanitize_windows_basename(name: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not name:
        return "_", ["Empty name replaced with '_'."]
    original = name
    cleaned = _WIN_INVALID.sub("_", name)
    cleaned = cleaned.rstrip(" .") or "_"
    if cleaned != original:
        warnings.append("Adjusted characters illegal on Windows or trailing space/dot.")
    if os.name == "nt" and len(cleaned) > 200:
        warnings.append("Basename is very long for Windows paths.")
    return cleaned, warnings


def warn_path_length(rel_posix: str) -> list[str]:
    w: list[str] = []
    if os.name == "nt" and len(rel_posix) > 230:
        w.append("Full relative path is long; may approach Windows MAX_PATH limits.")
    return w


def unique_target_basename(
    archive_root: Path,
    dir_rel: str,
    desired_basename: str,
    allowed_prefixes: list[str],
    *,
    exclude_source_rel: str | None = None,
) -> tuple[str, list[str]]:
    """
    If desired basename exists in folder (and is not the source file), append _2, _3, …
    before extension.
    """
    warnings: list[str] = []
    stem, ext = split_basename(desired_basename)
    parent = assert_allowed_path(archive_root, dir_rel, allowed_prefixes)
    src_resolved: Path | None = None
    if exclude_source_rel:
        try:
            src_resolved = assert_allowed_path(
                archive_root, exclude_source_rel, allowed_prefixes
            ).resolve()
        except PathNotAllowedError:
            src_resolved = None
    candidate = desired_basename
    n = 1
    while True:
        target = parent / candidate
        if not target.exists():
            return candidate, warnings
        if src_resolved is not None:
            try:
                if target.resolve() == src_resolved:
                    return candidate, warnings
            except OSError:
                pass
        n += 1
        warnings.append("Collision: added numeric suffix before extension.")
        candidate = f"{stem}_{n}{ext}"


_preview_lock = threading.Lock()
_preview_store: dict[str, dict[str, Any]] = {}


def _purge_expired_unlocked(now: float) -> None:
    dead = [k for k, v in _preview_store.items() if v.get("expires_unix", 0) < now]
    for k in dead:
        del _preview_store[k]


def store_preview(
    rows: list[dict[str, Any]],
    *,
    operation: str = "translate_stem_deepl",
) -> str:
    pid = secrets.token_urlsafe(16)
    now = time.time()
    with _preview_lock:
        _purge_expired_unlocked(now)
        _preview_store[pid] = {
            "expires_unix": now + PREVIEW_TTL_SEC,
            "rows": rows,
            "operation": operation,
        }
    return pid


def get_preview(preview_id: str) -> list[dict[str, Any]] | None:
    now = time.time()
    with _preview_lock:
        _purge_expired_unlocked(now)
        ent = _preview_store.get(preview_id)
        if not ent:
            return None
        if ent["expires_unix"] < now:
            del _preview_store[preview_id]
            return None
        return ent["rows"]


def pop_preview(preview_id: str) -> tuple[list[dict[str, Any]], str] | None:
    now = time.time()
    with _preview_lock:
        _purge_expired_unlocked(now)
        ent = _preview_store.pop(preview_id, None)
        if not ent:
            return None
        if ent["expires_unix"] < now:
            return None
        op = str(ent.get("operation") or "rename")
        return ent["rows"], op


def _tag_summary_line(tags: dict[str, Any]) -> str:
    parts: list[str] = []
    for k in (
        "EXIF:DateTimeOriginal",
        "EXIF:CreateDate",
        "QuickTime:CreateDate",
        "Model",
        "EXIF:Model",
        "LensModel",
        "ImageSize",
    ):
        v = tags.get(k)
        if v is not None and str(v).strip():
            parts.append(f"{k}={v}")
            if len(parts) >= 5:
                break
    return "; ".join(parts)[:240]


def _pipeline_operation_label(steps: list[str]) -> str:
    m = {"exif": "apply_exif_template", "deepl": "translate_stem_deepl"}
    return "+".join(m[s] for s in steps) if steps else "rename"


def build_rename_preview(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    rels: list[str],
    opt: RenamePreviewOptions,
    stored_api_key: str,
    endpoint_mode: str,
    source_lang: str,
    target_lang: str,
    max_files: int = MAX_FILES_DEFAULT,
    exiftool_exe: str = "",
    exiftool_timeout_sec: float = 45.0,
) -> dict[str, Any]:
    rels_clean = [normalize_rel(r) for r in rels if (r or "").strip()]
    rels_clean = [r for r in rels_clean if r]
    cap = max(1, min(max_files, MAX_FILES_HARD))
    if len(rels_clean) > cap:
        raise ValueError(f"Too many files (max {cap} per preview).")

    if not opt.use_deepl and not opt.use_exif:
        raise ValueError("Enable at least one of DeepL or Exif metadata template.")
    if opt.use_exif and not (opt.exif_template or "").strip():
        raise ValueError("Exif template is empty.")
    if opt.use_deepl:
        api_key = effective_deepl_api_key(stored_api_key)
        if not api_key:
            raise ValueError(
                "DeepL API key is not set. Add it under Settings (Rename / DeepL) or set "
                "ARCHIVE_CONSOLE_DEEPL_API_KEY in the environment."
            )

    deepl_opt = opt.deepl_sub()
    order_seq = (
        ["exif", "deepl"]
        if opt.pipeline_order == "exif_then_deepl"
        else ["deepl", "exif"]
    )
    steps: list[str] = []
    for s in order_seq:
        if s == "exif" and opt.use_exif:
            steps.append("exif")
        elif s == "deepl" and opt.use_deepl:
            steps.append("deepl")

    et_bin = resolve_exiftool_bin(exiftool_exe)

    @dataclass
    class _Work:
        rel: str
        original_basename: str
        stem0: str
        ext: str
        dir_rel: str
        path_error: str | None = None
        tags: dict[str, Any] = field(default_factory=dict)
        exif_err: str = ""
        exif_stderr: str = ""
        tag_line: str = ""
        row_abort: str = ""

    works: list[_Work] = []
    for rel_raw in rels_clean:
        rel = normalize_rel(rel_raw)
        if not rel:
            continue
        try:
            full = assert_allowed_path(archive_root, rel, allowed_prefixes)
        except PathNotAllowedError as e:
            works.append(
                _Work(
                    rel=rel_raw,
                    original_basename="",
                    stem0="",
                    ext="",
                    dir_rel="",
                    path_error=str(e),
                )
            )
            continue
        if not full.is_file():
            works.append(
                _Work(
                    rel=rel,
                    original_basename="",
                    stem0="",
                    ext="",
                    dir_rel="",
                    path_error="not a file",
                )
            )
            continue
        name = full.name
        stem, ext = split_basename(name)
        dir_rel = str(full.parent.relative_to(archive_root.resolve()).as_posix())
        if dir_rel == ".":
            dir_rel = ""
        w = _Work(
            rel=rel,
            original_basename=name,
            stem0=stem,
            ext=ext,
            dir_rel=dir_rel,
        )
        if opt.use_exif:
            tags, stderr, err = run_exiftool_json(
                full,
                exiftool_bin=et_bin,
                timeout_sec=exiftool_timeout_sec,
            )
            w.exif_stderr = (stderr or "")[-500:]
            if err:
                w.exif_err = err
            elif tags:
                w.tags = tags
                w.tag_line = _tag_summary_line(tags)
        works.append(w)

    stems = [w.stem0 for w in works]
    usage: dict[str, Any] = {}

    for step in steps:
        if step == "exif":
            new_stems: list[str] = []
            for i, w in enumerate(works):
                if w.path_error or w.exif_err:
                    new_stems.append(stems[i])
                    continue
                used: dict[str, str] = {}
                rendered, rw = render_exif_template(
                    opt.exif_template.strip(),
                    w.tags,
                    pipeline_stem=stems[i],
                    used_tags=used,
                )
                rendered = forbid_path_seps(rendered).strip()
                if not rendered:
                    if opt.exif_missing_policy == "skip":
                        w.row_abort = (
                            "exif template empty or missing tags (policy: skip)"
                        )
                        new_stems.append(stems[i])
                        continue
                    rw.append("empty template output; kept previous stem")
                    new_stems.append(stems[i])
                else:
                    new_stems.append(rendered)
                    extra = json.dumps(used, ensure_ascii=False)[:180]
                    w.tag_line = (w.tag_line + " | " + extra)[:400]
                for x in rw:
                    w.tag_line = (w.tag_line + "; " + x)[:400]
            stems = new_stems
        elif step == "deepl":
            batch_map: list[tuple[int, str, str, str, list[str]]] = []
            batch_mid: list[str] = []
            for i, w in enumerate(works):
                if w.path_error or w.row_abort:
                    continue
                pr, mid, suf, br = prepare_deepl_input(
                    stems[i],
                    whole_basename=deepl_opt.whole_basename,
                    preserve_youtube_id=deepl_opt.preserve_youtube_id,
                    preserve_brackets=deepl_opt.preserve_brackets,
                )
                if not (mid or "").strip():
                    continue
                batch_map.append((i, pr, mid, suf, br))
                batch_mid.append(mid)
            translated: list[str] = []
            if batch_mid:
                api_key = effective_deepl_api_key(stored_api_key)
                base = resolve_deepl_base_url(api_key, endpoint_mode)
                translated, usage = translate_texts(
                    batch_mid,
                    api_key=api_key,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    endpoint_base=base,
                )
            new_stems = list(stems)
            for bi, (i, pr, _mid, suf, br) in enumerate(batch_map):
                new_mid = unshield_brackets(translated[bi], br)
                new_stems[i] = pr + new_mid + suf
            stems = new_stems

    rows_out: list[dict[str, Any]] = []
    snapshot: list[dict[str, Any]] = []

    for i, w in enumerate(works):
        warnings: list[str] = []
        warnings.extend(warn_path_length(w.rel))
        tags_preview = w.tag_line or "—"
        if w.path_error:
            rows_out.append(
                {
                    "rel": w.rel,
                    "original_basename": w.original_basename or Path(w.rel).name,
                    "proposed_basename": None,
                    "proposed_rel": None,
                    "status": "error",
                    "warnings": [w.path_error],
                    "tags_preview": tags_preview,
                    "exiftool_stderr": "",
                }
            )
            continue
        if w.exif_err:
            rows_out.append(
                {
                    "rel": w.rel,
                    "original_basename": w.original_basename,
                    "proposed_basename": None,
                    "proposed_rel": None,
                    "status": "error",
                    "warnings": [f"exiftool: {w.exif_err}"],
                    "tags_preview": tags_preview,
                    "exiftool_stderr": w.exif_stderr,
                }
            )
            continue
        if w.row_abort:
            rows_out.append(
                {
                    "rel": w.rel,
                    "original_basename": w.original_basename,
                    "proposed_basename": None,
                    "proposed_rel": None,
                    "status": "error",
                    "warnings": [w.row_abort],
                    "tags_preview": tags_preview,
                    "exiftool_stderr": w.exif_stderr,
                }
            )
            continue

        stem_final = stems[i]
        if opt.use_deepl:
            _pr, mid_check, _suf, _br = prepare_deepl_input(
                stem_final,
                whole_basename=deepl_opt.whole_basename,
                preserve_youtube_id=deepl_opt.preserve_youtube_id,
                preserve_brackets=deepl_opt.preserve_brackets,
            )
            if not (mid_check or "").strip():
                rows_out.append(
                    {
                        "rel": w.rel,
                        "original_basename": w.original_basename,
                        "proposed_basename": None,
                        "proposed_rel": None,
                        "status": "error",
                        "warnings": ["nothing to translate (DeepL segment empty)"],
                        "tags_preview": tags_preview,
                        "exiftool_stderr": w.exif_stderr,
                    }
                )
                continue

        prop_base, sw = sanitize_windows_basename(stem_final + w.ext)
        warnings.extend(sw)
        if prop_base == w.original_basename:
            warnings.append("Proposed name matches original (no change needed).")

        prop_base2, cw = unique_target_basename(
            archive_root,
            w.dir_rel,
            prop_base,
            allowed_prefixes,
            exclude_source_rel=w.rel,
        )
        warnings.extend(cw)
        prop_rel = (
            f"{w.dir_rel}/{prop_base2}" if w.dir_rel else prop_base2
        ).replace("\\", "/")

        rows_out.append(
            {
                "rel": w.rel,
                "original_basename": w.original_basename,
                "proposed_basename": prop_base2,
                "proposed_rel": prop_rel,
                "status": "ok" if not warnings else "warn",
                "warnings": warnings,
                "tags_preview": tags_preview,
                "exiftool_stderr": w.exif_stderr,
            }
        )
        snapshot.append(
            {
                "rel": w.rel,
                "original_basename": w.original_basename,
                "proposed_basename": prop_base2,
                "proposed_rel": prop_rel,
                "dir_rel": w.dir_rel,
            }
        )

    op_label = _pipeline_operation_label(steps)
    preview_id = store_preview(snapshot, operation=op_label)
    return {
        "preview_id": preview_id,
        "rows": rows_out,
        "usage": usage,
        "operation": op_label,
        "pipeline_order": opt.pipeline_order,
        "plan_note": "Steps: "
        + ", ".join(steps)
        + ". Fold order in build_rename_preview; add regex/counter steps here later.",
    }


def build_deepl_preview(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    rels: list[str],
    opt: RenameTranslateDeepLOptions,
    stored_api_key: str,
    endpoint_mode: str,
    source_lang: str,
    target_lang: str,
    max_files: int = MAX_FILES_DEFAULT,
) -> dict[str, Any]:
    popt = RenamePreviewOptions(
        whole_basename=opt.whole_basename,
        preserve_youtube_id=opt.preserve_youtube_id,
        preserve_brackets=opt.preserve_brackets,
        use_deepl=True,
        use_exif=False,
    )
    return build_rename_preview(
        archive_root=archive_root,
        allowed_prefixes=allowed_prefixes,
        rels=rels,
        opt=popt,
        stored_api_key=stored_api_key,
        endpoint_mode=endpoint_mode,
        source_lang=source_lang,
        target_lang=target_lang,
        max_files=max_files,
        exiftool_exe="",
        exiftool_timeout_sec=45.0,
    )


def apply_rename_preview(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    preview_id: str,
) -> tuple[dict[str, Any], str]:
    """
    Apply a prior preview: re-validate allowlisted paths, then Path.rename (atomic per file).
    We never use ExifTool to perform renames — only to read tags during preview.
    """
    popped = pop_preview(preview_id)
    if not popped:
        raise ValueError("Unknown or expired preview. Run preview again.")
    rows, pipeline_operation = popped

    items: list[dict[str, Any]] = []
    ok = skip = fail = 0
    for row in rows:
        rel = row["rel"]
        orig_base = row["original_basename"]
        proposed_base = row["proposed_basename"]
        proposed_rel = row["proposed_rel"]
        try:
            src = assert_allowed_path(archive_root, rel, allowed_prefixes)
        except PathNotAllowedError as e:
            fail += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "fail",
                    "reason": str(e),
                }
            )
            continue
        if not src.is_file():
            fail += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "fail",
                    "reason": "source missing",
                }
            )
            continue
        if src.name != orig_base:
            fail += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "fail",
                    "reason": "basename changed since preview",
                }
            )
            continue
        if proposed_base == orig_base:
            skip += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "skip",
                    "reason": "no change",
                }
            )
            continue
        try:
            dst = assert_allowed_path(archive_root, proposed_rel, allowed_prefixes)
        except PathNotAllowedError as e:
            fail += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "fail",
                    "reason": f"target not allowed: {e}",
                }
            )
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            fail += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "fail",
                    "reason": "target exists",
                }
            )
            continue
        try:
            src.rename(dst)
        except OSError as e:
            fail += 1
            items.append(
                {
                    "rel": rel,
                    "old_basename": orig_base,
                    "new_basename": proposed_base,
                    "status": "fail",
                    "reason": str(e),
                }
            )
            continue
        ok += 1
        items.append(
            {
                "rel": rel,
                "old_basename": orig_base,
                "new_basename": proposed_base,
                "status": "ok",
                "reason": "",
            }
        )

    run_id = str(uuid.uuid4())
    summary = {
        "run_id": run_id,
        "ok": ok,
        "skip": skip,
        "fail": fail,
        "items": items,
    }
    return summary, pipeline_operation
