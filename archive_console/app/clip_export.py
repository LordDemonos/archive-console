"""Local clip export via ffmpeg (allowlisted paths only)."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from .file_serve import assert_reports_file_not_sensitive, is_playable_media_path
from .paths import PathNotAllowedError, assert_allowed_path, is_allowed, normalize_rel
from .settings import ConsoleState, append_history

logger = logging.getLogger(__name__)

MAX_SEGMENT_SEC = 600.0
STDERR_TAIL_MAX = 4000
ClipFormat = Literal["mp4", "webm", "gif"]

_BAD_FFMPEG_EXE_CHARS = re.compile(r"[\r\n;&|<>`\"$]")


def validate_ffmpeg_exe_setting(raw: str | None) -> str:
    """Strip; empty allowed; reject obvious shell metacharacters."""
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if _BAD_FFMPEG_EXE_CHARS.search(s):
        raise ValueError("ffmpeg_exe must be a single path (no shell metacharacters)")
    if len(s) > 512:
        raise ValueError("ffmpeg_exe path too long")
    return s


def resolve_ffmpeg_bin(st: ConsoleState) -> str:
    v = (st.ffmpeg_exe or "").strip()
    return v if v else "ffmpeg"


def validate_clip_times(
    start_sec: float,
    *,
    end_sec: float | None = None,
    duration_sec: float | None = None,
) -> float:
    """Return segment duration in seconds."""
    if not isinstance(start_sec, (int, float)) or start_sec != start_sec:  # nan
        raise ValueError("invalid start_sec")
    if start_sec < 0:
        raise ValueError("start_sec must be >= 0")
    if end_sec is not None and duration_sec is not None:
        raise ValueError("provide either end_sec or duration_sec, not both")
    if end_sec is not None:
        if not isinstance(end_sec, (int, float)) or end_sec != end_sec:
            raise ValueError("invalid end_sec")
        if end_sec <= start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        d = end_sec - start_sec
    elif duration_sec is not None:
        if not isinstance(duration_sec, (int, float)) or duration_sec != duration_sec:
            raise ValueError("invalid duration_sec")
        if duration_sec <= 0:
            raise ValueError("duration_sec must be positive")
        d = float(duration_sec)
    else:
        raise ValueError("end_sec or duration_sec required")
    if d > MAX_SEGMENT_SEC:
        raise ValueError(f"segment longer than {int(MAX_SEGMENT_SEC)}s not allowed")
    return d


_SAFE_BASENAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,200}$")


def safe_output_basename(
    stem: str,
    fmt: ClipFormat,
    *,
    fallback_stem: str,
) -> str:
    """Return filename stem (no extension) safe for disk."""
    from datetime import datetime, timezone

    s = (stem or "").strip()
    if not s:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = re.sub(r"[^a-zA-Z0-9._-]+", "_", fallback_stem)[:80].strip("._-") or "clip"
        s = f"{base}_{ts}"
    if not _SAFE_BASENAME_RE.match(s):
        raise ValueError(
            "basename must be 1–200 chars: letters, digits, . _ - only"
        )
    return s


def build_ffmpeg_argv(
    ffmpeg_bin: str,
    input_abs: Path,
    output_abs: Path,
    start_sec: float,
    duration_sec: float,
    fmt: ClipFormat,
) -> list[str]:
    """Build ffmpeg argv (no shell)."""
    i = str(input_abs)
    o = str(output_abs)
    if fmt == "mp4":
        return [
            ffmpeg_bin,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-ss",
            f"{start_sec:.6f}",
            "-i",
            i,
            "-t",
            f"{duration_sec:.6f}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            o,
        ]
    if fmt == "webm":
        return [
            ffmpeg_bin,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-ss",
            f"{start_sec:.6f}",
            "-i",
            i,
            "-t",
            f"{duration_sec:.6f}",
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "30",
            "-b:v",
            "0",
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            o,
        ]
    if fmt == "gif":
        vf = (
            "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];"
            "[s0]palettegen=reserve_transparent=0[p];[s1][p]paletteuse"
        )
        return [
            ffmpeg_bin,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-ss",
            f"{start_sec:.6f}",
            "-i",
            i,
            "-t",
            f"{duration_sec:.6f}",
            "-vf",
            vf,
            "-loop",
            "0",
            o,
        ]
    raise ValueError(f"unknown format: {fmt}")


def _suffix_for_fmt(fmt: ClipFormat) -> str:
    return f".{fmt}"


def resolve_clip_paths(
    archive_root: Path,
    allowed_prefixes: list[str],
    source_rel: str,
    output_dir_rel: str,
    basename_stem: str,
    fmt: ClipFormat,
) -> tuple[Path, Path, str]:
    """
    Validate I/O paths. Returns (input_abs, output_abs, output_rel posix).
    Raises PathNotAllowedError, ValueError, HTTPException (cookies).
    """
    root = archive_root.resolve()
    src_full = assert_allowed_path(root, source_rel, allowed_prefixes)
    if not src_full.is_file():
        raise ValueError("source is not a file")
    assert_reports_file_not_sensitive(src_full)
    if not is_playable_media_path(src_full):
        raise ValueError("source is not a supported video/audio type for clipping")

    out_dir = assert_allowed_path(root, output_dir_rel, allowed_prefixes)
    if not out_dir.is_dir():
        raise ValueError("output_dir_rel must be an existing directory")

    stem = safe_output_basename(
        basename_stem, fmt, fallback_stem=src_full.stem
    )
    name = stem + _suffix_for_fmt(fmt)
    out_full = (out_dir / name).resolve()
    try:
        out_full.relative_to(root)
    except ValueError as e:
        raise PathNotAllowedError("outside archive root") from e
    if not is_allowed(root, out_full.parent, allowed_prefixes):
        raise PathNotAllowedError("not on allowlist")
    if out_full.exists():
        raise ValueError("output file already exists; choose a different basename")
    assert_reports_file_not_sensitive(out_full)
    out_rel = out_full.relative_to(root).as_posix()
    return src_full, out_full, out_rel


class ClipPhase(str, Enum):
    idle = "idle"
    running = "running"
    success = "success"
    failed = "failed"


@dataclass
class ClipRunState:
    clip_id: str
    phase: ClipPhase
    started_unix: float
    ended_unix: float | None = None
    exit_code: int | None = None
    stderr_tail: str = ""
    source_rel: str = ""
    output_rel: str | None = None
    clip_format: str = ""


@dataclass
class ClipExportManager:
    """Single-flight ffmpeg clip jobs (independent of RunManager)."""

    get_state: Callable[[], ConsoleState]
    persist_state: Callable[[ConsoleState], None]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _current: ClipRunState | None = None
    _task: asyncio.Task[None] | None = None

    def status(self) -> dict[str, Any]:
        c = self._current
        if c is None:
            return {"phase": ClipPhase.idle.value, "clip": None}
        return {
            "phase": c.phase.value,
            "clip": {
                "clip_id": c.clip_id,
                "started_unix": c.started_unix,
                "ended_unix": c.ended_unix,
                "exit_code": c.exit_code,
                "stderr_tail": c.stderr_tail,
                "source_rel": c.source_rel,
                "output_rel": c.output_rel,
                "format": c.clip_format,
            },
        }

    async def start(
        self,
        *,
        source_rel: str,
        output_dir_rel: str,
        start_sec: float,
        end_sec: float | None,
        duration_sec: float | None,
        fmt: ClipFormat,
        basename: str,
    ) -> str:
        async with self._lock:
            if self._current is not None and self._current.phase == ClipPhase.running:
                raise RuntimeError("A clip export is already running")
            st = self.get_state()
            root = Path(st.archive_root).expanduser().resolve()
            prefixes = st.allowlisted_rel_prefixes
            try:
                src_n = normalize_rel(source_rel.strip())
            except PathNotAllowedError as e:
                raise ValueError(str(e)) from e
            try:
                out_n = normalize_rel(output_dir_rel.strip())
            except PathNotAllowedError as e:
                raise ValueError(str(e)) from e
            dur = validate_clip_times(
                start_sec, end_sec=end_sec, duration_sec=duration_sec
            )
            src_abs, out_abs, out_rel = resolve_clip_paths(
                root, prefixes, src_n, out_n, basename, fmt
            )
            ffmpeg_bin = resolve_ffmpeg_bin(st)
            argv = build_ffmpeg_argv(
                ffmpeg_bin, src_abs, out_abs, start_sec, dur, fmt
            )
            clip_id = uuid.uuid4().hex[:10]
            started_unix = time.time()
            self._current = ClipRunState(
                clip_id=clip_id,
                phase=ClipPhase.running,
                started_unix=started_unix,
                source_rel=src_n,
                output_rel=None,
                clip_format=fmt,
            )
            self._task = asyncio.create_task(
                self._run_subprocess(
                    argv=argv,
                    clip_id=clip_id,
                    started_unix=started_unix,
                    source_rel=src_n,
                    out_rel=out_rel,
                    fmt=fmt,
                )
            )
        return clip_id

    async def _run_subprocess(
        self,
        *,
        argv: list[str],
        clip_id: str,
        started_unix: float,
        source_rel: str,
        out_rel: str,
        fmt: str,
    ) -> None:
        tail_buf = bytearray()
        exit_code: int | None = None
        t0 = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            assert proc.stderr is not None
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                tail_buf.extend(chunk)
                if len(tail_buf) > STDERR_TAIL_MAX:
                    del tail_buf[: len(tail_buf) - STDERR_TAIL_MAX]
            exit_code = await proc.wait()
        except Exception as e:
            logger.warning("clip export %s subprocess error: %s", clip_id, e)
            exit_code = -1
            tail_buf.extend(str(e).encode("utf-8", errors="replace"))
        elapsed = time.time() - t0
        stderr_text = tail_buf.decode("utf-8", errors="replace")[-STDERR_TAIL_MAX:]
        success = exit_code == 0
        phase = ClipPhase.success if success else ClipPhase.failed
        async with self._lock:
            if self._current and self._current.clip_id == clip_id:
                self._current.phase = phase
                self._current.ended_unix = time.time()
                self._current.exit_code = exit_code
                self._current.stderr_tail = stderr_text
                self._current.output_rel = out_rel if success else None
        logger.info(
            "clip export done id=%s source=%s out=%s exit=%s duration_s=%.2f",
            clip_id,
            source_rel,
            out_rel if success else "—",
            exit_code,
            elapsed,
        )
        entry: dict[str, Any] = {
            "run_id": clip_id,
            "job": "clip_export",
            "started_unix": started_unix,
            "ended_unix": time.time(),
            "exit_code": exit_code,
            "phase": phase.value,
            "log_folder_rel": None,
            "clip_source_rel": source_rel,
            "clip_output_rel": out_rel if success else None,
            "clip_format": fmt,
            "clip_stderr_tail": stderr_text,
        }
        st = self.get_state()
        st2 = append_history(st, entry)
        self.persist_state(st2)

    async def join_idle(self) -> None:
        """Test helper: wait until no running task."""
        t = self._task
        if t and not t.done():
            await t
