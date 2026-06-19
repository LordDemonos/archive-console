"""Batch convert gallery videos to GIF via ffmpeg frames + gifski (Mp4ToGif-style)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .clip_export import resolve_ffmpeg_bin, validate_ffmpeg_exe_setting
from .download_output import effective_galleries_root, state_allowed_prefixes
from .gifski_setup import DEFAULT_STATE, model_from_client_dict, parse_gifsky_conf_text
from .paths import PathNotAllowedError, assert_allowed_path, is_allowed, normalize_rel
from .settings import ConsoleState, DownloadDirsSettings

logger = logging.getLogger(__name__)

MANIFEST_SUBDIR = "_gifsky/manifest.json"


def manifest_rel_for_galleries(galleries_root: Path, archive_root: Path) -> str:
    return galleries_root.relative_to(archive_root).joinpath(MANIFEST_SUBDIR).as_posix()
_LOG_MAX = 800
_BAD_EXE_CHARS = re.compile(r"[\r\n;&|<>`\"$]")


def validate_gifski_exe_setting(raw: str | None) -> str:
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if _BAD_EXE_CHARS.search(s):
        raise ValueError("gifski_exe must be a single path (no shell metacharacters)")
    if len(s) > 512:
        raise ValueError("gifski_exe path too long")
    return s


def resolve_gifski_bin(st: ConsoleState) -> str:
    v = (getattr(st, "gifski_exe", None) or "").strip()
    return v if v else "gifski"


@dataclass
class ScanVideo:
    rel: str
    size_bytes: int
    has_gif: bool
    gif_bytes: int | None = None
    skipped_reason: str | None = None


@dataclass
class ScanFolder:
    rel: str
    videos: list[ScanVideo]
    pending_count: int
    gif_count: int


def _gifsky_conf_from_state(st: ConsoleState) -> dict[str, Any]:
    root = Path(st.archive_root).expanduser().resolve()
    p = root / "gifsky.conf"
    text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    conf, _w = parse_gifsky_conf_text(text)
    return conf


def _video_suffixes(conf: dict[str, Any]) -> set[str]:
    return {"." + e.lower().lstrip(".") for e in conf.get("extensions") or []}


def build_size_comparison(video_bytes: int, gif_bytes: int) -> dict[str, Any]:
    """Compare on-disk video vs GIF sizes (negative delta_pct = GIF smaller)."""
    vb = max(0, int(video_bytes))
    gb = max(0, int(gif_bytes))
    if vb <= 0:
        return {
            "video_bytes": vb,
            "gif_bytes": gb,
            "delta_bytes": gb - vb,
            "ratio": None,
            "delta_pct": None,
            "label": "",
        }
    delta = gb - vb
    ratio = round(gb / vb, 3) if vb else None
    delta_pct = round(100.0 * delta / vb, 1)
    if delta_pct > 0:
        label = f"{delta_pct:+.1f}% vs video"
    elif delta_pct < 0:
        label = f"{delta_pct:.1f}% vs video"
    else:
        label = "same size as video"
    return {
        "video_bytes": vb,
        "gif_bytes": gb,
        "delta_bytes": delta,
        "ratio": ratio,
        "delta_pct": delta_pct,
        "label": label,
    }


def _aggregate_size_comparison(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    vb = sum(int(x.get("video_bytes") or x.get("size_bytes") or 0) for x in items)
    gb = sum(int(x.get("gif_bytes") or 0) for x in items)
    if not items or vb <= 0:
        return None
    out = build_size_comparison(vb, gb)
    out["paired_count"] = len(items)
    return out


def format_size_pair_line(video_bytes: int, gif_bytes: int) -> str:
    comp = build_size_comparison(video_bytes, gif_bytes)

    def _fmt(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.2f} MB"

    vb, gb = comp["video_bytes"], comp["gif_bytes"]
    tail = comp["label"] or ""
    return f"{_fmt(vb)} → {_fmt(gb)}" + (f" ({tail})" if tail else "")


def _rollup_gallery_folder_key(folder_rel: str) -> str:
    """
    Group nested gallery-dl paths (e.g. …/reddit_user_foo/redgifs/image) under
    the RipMe-style reddit_user_* / reddit_sub_* folder for scan summaries.
    """
    parts = folder_rel.replace("\\", "/").split("/")
    for i, seg in enumerate(parts):
        if seg.startswith("reddit_user_") or seg.startswith("reddit_sub_"):
            return "/".join(parts[: i + 1])
    return folder_rel.replace("\\", "/")


def scan_gallery_videos(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    download_dirs: DownloadDirsSettings,
    conf: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = archive_root.expanduser().resolve()
    conf = model_from_client_dict(conf or DEFAULT_STATE)
    gal_root = effective_galleries_root(root, download_dirs)
    if not is_allowed(root, gal_root, allowed_prefixes):
        raise PathNotAllowedError(
            "galleries output folder is not under the archive root or download output folders"
        )
    gal_rel = gal_root.relative_to(root).as_posix()
    suffixes = _video_suffixes(conf)
    max_bytes = int(float(conf["max_source_mb"]) * 1048576) if conf["max_source_mb"] else 0
    skip_gif = bool(conf["skip_if_gif_exists"])

    by_folder: dict[str, list[ScanVideo]] = {}
    totals = {"videos": 0, "pending": 0, "gifs": 0, "skipped": 0}

    if not gal_root.is_dir():
        return {
            "galleries_root_rel": gal_rel,
            "folders": [],
            "totals": totals,
        }

    for path in sorted(gal_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in suffixes:
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if not is_allowed(root, path, allowed_prefixes):
            continue
        folder_rel = path.parent.relative_to(root).as_posix()
        group_rel = _rollup_gallery_folder_key(folder_rel)
        gif_path = path.with_suffix(".gif")
        has_gif = gif_path.is_file()
        gif_bytes: int | None = gif_path.stat().st_size if has_gif else None
        size = path.stat().st_size
        skipped: str | None = None
        pending = True
        if max_bytes and size > max_bytes:
            skipped = f"over {conf['max_source_mb']} MB"
            pending = False
            totals["skipped"] += 1
        elif skip_gif and has_gif:
            skipped = "gif exists"
            pending = False
            totals["skipped"] += 1
        if pending:
            totals["pending"] += 1
        if has_gif:
            totals["gifs"] += 1
        totals["videos"] += 1
        entry = ScanVideo(
            rel=rel,
            size_bytes=size,
            has_gif=has_gif,
            gif_bytes=gif_bytes,
            skipped_reason=skipped,
        )
        by_folder.setdefault(group_rel, []).append(entry)

    folders: list[dict[str, Any]] = []
    for folder_rel in sorted(by_folder.keys()):
        vids = by_folder[folder_rel]
        pending_n = sum(1 for v in vids if v.skipped_reason is None)
        gif_n = sum(1 for v in vids if v.has_gif)
        folders.append(
            {
                "rel": folder_rel,
                "pending_count": pending_n,
                "gif_count": gif_n,
                "video_count": len(vids),
                "video_bytes": sum(v.size_bytes for v in vids),
                "pending_video_bytes": sum(
                    v.size_bytes for v in vids if v.skipped_reason is None
                ),
                "videos": [
                    (lambda v: {
                        "rel": v.rel,
                        "size_bytes": v.size_bytes,
                        "has_gif": v.has_gif,
                        "gif_bytes": v.gif_bytes,
                        "skipped_reason": v.skipped_reason,
                        **(
                            {
                                "size_comparison": build_size_comparison(
                                    v.size_bytes, v.gif_bytes or 0
                                )
                            }
                            if v.has_gif and v.gif_bytes is not None
                            else {}
                        ),
                    })(v)
                    for v in vids
                ],
            }
        )
    for folder in folders:
        paired = [
            v
            for v in folder["videos"]
            if v.get("has_gif") and v.get("gif_bytes") is not None
        ]
        comp = _aggregate_size_comparison(paired)
        folder["size_comparison"] = comp

    paired_all: list[dict[str, Any]] = []
    for folder in folders:
        for v in folder["videos"]:
            if v.get("has_gif") and v.get("gif_bytes") is not None:
                paired_all.append(v)
    totals_comp = _aggregate_size_comparison(paired_all)

    warnings: list[str] = []
    if gal_root.is_dir():
        legacy_frames = 0
        for pat in ("*_frame*.png", "*_frame*.jpg", "*_frame*.jpeg"):
            legacy_frames += sum(1 for _ in gal_root.rglob(pat))
        if legacy_frames:
            warnings.append(
                f"Found {legacy_frames} leftover Gifsky frame file(s) "
                "(videoname_frameNNNN.png/jpg) — re-run convert or delete manually; "
                "new runs auto-clean these."
            )
    if gal_root.is_dir() and ".m4v" not in suffixes:
        missed = sum(1 for p in gal_root.rglob("*.m4v") if p.is_file())
        if missed:
            warnings.append(
                f"Found {missed} .m4v file(s) under galleries but .m4v is not in "
                "gifsky.conf extensions — Reddit / RedGifs often use .m4v."
            )

    return {
        "galleries_root_rel": gal_rel,
        "folders": folders,
        "totals": totals,
        "size_comparison": totals_comp,
        "conf_summary": conf,
        "scan_warnings": warnings,
    }


_FRAME_GLOBS = ("frame*.png", "frame*.jpg", "frame*.jpeg", "frame*.PNG", "frame*.JPG")
_LEGACY_FRAME_GLOBS = (
    "{stem}_frame*.png",
    "{stem}_frame*.jpg",
    "{stem}_frame*.jpeg",
)


def _safe_stem_for_dir(stem: str) -> str:
    s = re.sub(r"[^\w.-]+", "_", stem).strip("._-")[:60]
    return s or "video"


def _make_gifsky_frames_dir(parent: Path, stem: str) -> Path:
    """Isolated work dir beside the video — removed entirely after each convert."""
    name = f".gifsky_{_safe_stem_for_dir(stem)}_{uuid.uuid4().hex[:8]}"
    frames_dir = parent / name
    frames_dir.mkdir(parents=True, exist_ok=False)
    return frames_dir


def _collect_frame_paths(frames_dir: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in _FRAME_GLOBS:
        for path in frames_dir.glob(pattern):
            rp = path.resolve()
            if rp not in seen and path.is_file():
                seen.add(rp)
                found.append(path)
    return sorted(found)


def _remove_gifsky_work_dir(frames_dir: Path | None) -> None:
    if frames_dir is None:
        return
    shutil.rmtree(frames_dir, ignore_errors=True)


def _cleanup_legacy_frame_files(parent: Path, stem: str) -> int:
    """Remove pre-refactor frames written next to the source video."""
    removed = 0
    for pattern in _LEGACY_FRAME_GLOBS:
        for path in parent.glob(pattern.format(stem=stem)):
            if not path.is_file():
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _build_ffmpeg_frames_argv(
    ffmpeg_bin: str,
    source: Path,
    frames_dir: Path,
    frame_pattern: str,
    scale_max_width: int,
) -> list[str]:
    out_pattern = str(frames_dir / frame_pattern)
    argv = [
        ffmpeg_bin,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(source),
    ]
    if scale_max_width > 0:
        argv.extend(["-vf", f"scale={scale_max_width}:-1:flags=lanczos"])
    argv.append(out_pattern)
    return argv


def convert_one_video(
    *,
    source_abs: Path,
    conf: dict[str, Any],
    ffmpeg_bin: str,
    gifski_bin: str,
    delete_source: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Convert a single video; returns result dict (no raise on failure)."""
    conf = model_from_client_dict(conf)
    gif_abs = source_abs.with_suffix(".gif")
    rel = source_abs.name
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "source": rel,
            "gif_rel": gif_abs.name,
        }

    frames_dir: Path | None = None
    stem = source_abs.stem
    try:
        frames_dir = _make_gifsky_frames_dir(source_abs.parent, stem)
        frame_pattern = "frame%04d.png"
        argv = _build_ffmpeg_frames_argv(
            ffmpeg_bin,
            source_abs,
            frames_dir,
            frame_pattern,
            int(conf["ffmpeg_scale_max_width"]),
        )
        proc = __import__("subprocess").run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "source": rel,
                "stage": "ffmpeg",
                "error": (proc.stderr or proc.stdout or "ffmpeg failed")[-2000:],
            }

        frames = _collect_frame_paths(frames_dir)
        if not frames:
            return {
                "ok": False,
                "source": rel,
                "stage": "ffmpeg",
                "error": "no frame images produced",
            }

        gifski_argv = [
            gifski_bin,
            "--fps",
            str(conf["fps"]),
            "--quality",
            str(conf["quality"]),
            "-o",
            str(gif_abs),
            *[str(f) for f in frames],
        ]
        proc2 = __import__("subprocess").run(
            gifski_argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc2.returncode != 0:
            return {
                "ok": False,
                "source": rel,
                "stage": "gifski",
                "error": (proc2.stderr or proc2.stdout or "gifski failed")[-2000:],
            }

        if not gif_abs.is_file():
            return {
                "ok": False,
                "source": rel,
                "stage": "verify",
                "error": "GIF file missing after gifski",
            }
        gif_size = gif_abs.stat().st_size
        if gif_size < int(conf["verify_min_bytes"]):
            try:
                gif_abs.unlink(missing_ok=True)
            except OSError:
                pass
            return {
                "ok": False,
                "source": rel,
                "stage": "verify",
                "error": f"GIF too small ({gif_size} bytes)",
            }

        source_bytes = source_abs.stat().st_size
        source_deleted = False
        if delete_source:
            try:
                source_abs.unlink()
                source_deleted = True
            except OSError as e:
                legacy = _cleanup_legacy_frame_files(source_abs.parent, stem)
                out_err: dict[str, Any] = {
                    "ok": True,
                    "source": rel,
                    "gif_bytes": gif_size,
                    "source_bytes": source_bytes,
                    "source_deleted": False,
                    "warn": f"GIF ok but could not delete source: {e}",
                }
                if legacy:
                    out_err["legacy_frames_removed"] = legacy
                return out_err

        legacy = _cleanup_legacy_frame_files(source_abs.parent, stem)
        out_ok: dict[str, Any] = {
            "ok": True,
            "source": rel,
            "gif_bytes": gif_size,
            "source_bytes": source_bytes,
            "source_deleted": source_deleted,
        }
        if legacy:
            out_ok["legacy_frames_removed"] = legacy
        return out_ok
    except OSError as e:
        return {"ok": False, "source": rel, "stage": "io", "error": str(e)}
    finally:
        _remove_gifsky_work_dir(frames_dir)


class GifskyPhase(str, Enum):
    idle = "idle"
    running = "running"
    success = "success"
    failed = "failed"
    canceled = "canceled"


@dataclass
class GifskyRunState:
    job_id: str
    phase: GifskyPhase
    started_unix: float
    ended_unix: float | None = None
    total: int = 0
    current_index: int = 0
    current_rel: str = ""
    converted: int = 0
    failed: int = 0
    skipped: int = 0
    delete_source: bool = False
    dry_run: bool = False
    batch_source_bytes: int = 0
    batch_gif_bytes: int = 0


@dataclass
class GifskyBatchManager:
    get_state: Callable[[], ConsoleState]
    persist_state: Callable[[ConsoleState], None]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _current: GifskyRunState | None = None
    _task: asyncio.Task[None] | None = None
    _logs: deque[str] = field(default_factory=lambda: deque(maxlen=_LOG_MAX))
    _cancel: bool = False

    def _log(self, line: str) -> None:
        self._logs.append(line)

    def status(self) -> dict[str, Any]:
        c = self._current
        if c is None:
            return {"phase": GifskyPhase.idle.value, "job": None, "logs": list(self._logs)}
        return {
            "phase": c.phase.value,
            "job": {
                "job_id": c.job_id,
                "started_unix": c.started_unix,
                "ended_unix": c.ended_unix,
                "total": c.total,
                "current_index": c.current_index,
                "current_rel": c.current_rel,
                "converted": c.converted,
                "failed": c.failed,
                "skipped": c.skipped,
                "delete_source": c.delete_source,
                "dry_run": c.dry_run,
                "size_comparison": build_size_comparison(
                    c.batch_source_bytes, c.batch_gif_bytes
                )
                if c.batch_gif_bytes > 0
                else None,
            },
            "logs": list(self._logs),
        }

    async def cancel(self) -> bool:
        async with self._lock:
            if self._current is None or self._current.phase != GifskyPhase.running:
                return False
            self._cancel = True
            return True

    async def start(
        self,
        *,
        delete_source_after_verify: bool,
        dry_run: bool,
        folder_rels: list[str] | None = None,
    ) -> str:
        async with self._lock:
            if self._current is not None and self._current.phase == GifskyPhase.running:
                raise RuntimeError("A gifsky batch is already running")
            st = self.get_state()
            root = Path(st.archive_root).expanduser().resolve()
            conf = _gifsky_conf_from_state(st)
            scan = scan_gallery_videos(
                archive_root=root,
                allowed_prefixes=state_allowed_prefixes(st),
                download_dirs=st.download_dirs,
                conf=conf,
            )
            pending: list[str] = []
            folder_filter = {normalize_rel(r) for r in (folder_rels or []) if r.strip()}
            for folder in scan.get("folders") or []:
                folder_rel = folder.get("rel") or ""
                if folder_filter and folder_rel not in folder_filter:
                    continue
                for v in folder.get("videos") or []:
                    if v.get("skipped_reason"):
                        continue
                    rel = v.get("rel") or ""
                    if rel:
                        pending.append(rel)

            job_id = uuid.uuid4().hex[:10]
            started = time.time()
            self._cancel = False
            self._logs.clear()
            self._current = GifskyRunState(
                job_id=job_id,
                phase=GifskyPhase.running,
                started_unix=started,
                total=len(pending),
                delete_source=delete_source_after_verify,
                dry_run=dry_run,
            )
            self._log(
                f"[gifsky] Starting batch — {len(pending)} video(s)"
                + (" (dry run)" if dry_run else "")
                + (" — delete source after verify" if delete_source_after_verify else "")
            )
            self._task = asyncio.create_task(
                self._run_batch(
                    pending=pending,
                    conf=conf,
                    delete_source=delete_source_after_verify,
                    dry_run=dry_run,
                    job_id=job_id,
                    started=started,
                )
            )
        return job_id

    async def _run_batch(
        self,
        *,
        pending: list[str],
        conf: dict[str, Any],
        delete_source: bool,
        dry_run: bool,
        job_id: str,
        started: float,
    ) -> None:
        st = self.get_state()
        root = Path(st.archive_root).expanduser().resolve()
        prefixes = state_allowed_prefixes(st)
        ffmpeg_bin = resolve_ffmpeg_bin(st)
        gifski_bin = resolve_gifski_bin(st)
        manifest_entries: list[dict[str, Any]] = []
        converted = failed = skipped = 0
        batch_source_bytes = 0
        batch_gif_bytes = 0

        try:
            for i, rel in enumerate(pending):
                if self._cancel:
                    self._log("[gifsky] Canceled by operator.")
                    break
                async with self._lock:
                    if self._current:
                        self._current.current_index = i + 1
                        self._current.current_rel = rel
                self._log(f"[gifsky] ({i + 1}/{len(pending)}) {rel}")
                try:
                    src_abs = assert_allowed_path(root, rel, prefixes)
                except PathNotAllowedError as e:
                    failed += 1
                    self._log(f"  FAIL allowlist: {e}")
                    continue
                if not src_abs.is_file():
                    skipped += 1
                    self._log("  SKIP missing file")
                    continue

                result = await asyncio.to_thread(
                    convert_one_video,
                    source_abs=src_abs,
                    conf=conf,
                    ffmpeg_bin=ffmpeg_bin,
                    gifski_bin=gifski_bin,
                    delete_source=delete_source,
                    dry_run=dry_run,
                )
                if result.get("dry_run"):
                    converted += 1
                    self._log("  (dry run — would convert)")
                    continue
                if result.get("ok"):
                    converted += 1
                    vb = int(result.get("source_bytes") or 0)
                    gb = int(result.get("gif_bytes") or 0)
                    if vb > 0 and gb > 0:
                        batch_source_bytes += vb
                        batch_gif_bytes += gb
                    self._log(f"  OK → {format_size_pair_line(vb, gb)}")
                    if result.get("legacy_frames_removed"):
                        self._log(
                            f"  Cleaned {result['legacy_frames_removed']} leftover frame file(s) from earlier runs"
                        )
                    if result.get("warn"):
                        self._log(f"  WARN {result['warn']}")
                    if result.get("source_deleted"):
                        self._log("  Removed source video")
                    manifest_entries.append(
                        {
                            "source_rel": rel,
                            "gif_rel": str(Path(rel).with_suffix(".gif")),
                            "source_bytes": vb,
                            "gif_bytes": gb,
                            "size_comparison": build_size_comparison(vb, gb),
                            "source_deleted": bool(result.get("source_deleted")),
                            "converted_unix": time.time(),
                            "job_id": job_id,
                        }
                    )
                else:
                    failed += 1
                    self._log(
                        f"  FAIL [{result.get('stage', '?')}] {result.get('error', 'unknown')}"
                    )

            if manifest_entries and not dry_run:
                gal_root = effective_galleries_root(root, st.download_dirs)
                manifest_rel = manifest_rel_for_galleries(gal_root, root)
                await asyncio.to_thread(
                    _append_manifest,
                    root,
                    prefixes,
                    manifest_rel,
                    manifest_entries,
                )

            phase = (
                GifskyPhase.canceled
                if self._cancel
                else (GifskyPhase.success if failed == 0 else GifskyPhase.failed)
            )
            summary = (
                f"[gifsky] Done — converted={converted} failed={failed} skipped={skipped}"
            )
            if batch_gif_bytes > 0 and batch_source_bytes > 0:
                summary += f" | batch size {format_size_pair_line(batch_source_bytes, batch_gif_bytes)}"
            self._log(summary)
        except Exception as e:
            logger.exception("gifsky batch failed")
            phase = GifskyPhase.failed
            self._log(f"[gifsky] Batch error: {e}")
        finally:
            async with self._lock:
                if self._current and self._current.job_id == job_id:
                    self._current.phase = phase
                    self._current.ended_unix = time.time()
                    self._current.converted = converted
                    self._current.failed = failed
                    self._current.skipped = skipped
                    self._current.batch_source_bytes = batch_source_bytes
                    self._current.batch_gif_bytes = batch_gif_bytes


def _append_manifest(
    archive_root: Path,
    allowed_prefixes: list[str],
    manifest_rel: str,
    entries: list[dict[str, Any]],
) -> None:
    manifest_abs = assert_allowed_path(archive_root, manifest_rel, allowed_prefixes)
    manifest_abs.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if manifest_abs.is_file():
        try:
            raw = json.loads(manifest_abs.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                existing = raw
        except (json.JSONDecodeError, OSError):
            existing = []
    existing.extend(entries)
    manifest_abs.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
