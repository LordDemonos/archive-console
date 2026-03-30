"""Single-flight duplicate scan (CPU/IO work in a thread pool)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .duplicate_scan import DuplicateGroup, find_duplicate_groups
from .paths import PathNotAllowedError, assert_allowed_path, normalize_rel
from .settings import ConsoleState

logger = logging.getLogger(__name__)


class DupScanPhase(str, Enum):
    idle = "idle"
    running = "running"
    success = "success"
    failed = "failed"


@dataclass
class DupScanState:
    scan_id: str
    phase: DupScanPhase
    started_unix: float
    ended_unix: float | None = None
    error: str | None = None
    stats: dict[str, int] | None = None
    groups: list[dict[str, Any]] | None = None


@dataclass
class DuplicateScanManager:
    get_state: Callable[[], ConsoleState]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _current: DupScanState | None = None
    _task: asyncio.Task[None] | None = None
    _progress: dict[str, int] = field(
        default_factory=lambda: {"files_scanned": 0, "files_hashed": 0, "groups_found": 0}
    )

    def status(self) -> dict[str, Any]:
        c = self._current
        prog = dict(self._progress)
        if c is None:
            return {
                "phase": DupScanPhase.idle.value,
                "scan": None,
                "progress": prog,
            }
        return {
            "phase": c.phase.value,
            "progress": prog,
            "scan": {
                "scan_id": c.scan_id,
                "started_unix": c.started_unix,
                "ended_unix": c.ended_unix,
                "error": c.error,
                "stats": c.stats,
                "groups": c.groups,
            },
        }

    async def start_scan(
        self,
        *,
        root_rels: list[str],
        include_video: bool,
        include_images: bool,
    ) -> str:
        async with self._lock:
            if self._current is not None and self._current.phase == DupScanPhase.running:
                raise RuntimeError("A duplicate scan is already running")

            st = self.get_state()
            root = Path(st.archive_root).expanduser().resolve()
            prefixes = st.allowlisted_rel_prefixes

            if not include_video and not include_images:
                raise ValueError("enable at least one of video or images")

            roots_norm: list[str] = []
            for raw in root_rels:
                try:
                    rel_n = normalize_rel(str(raw).strip())
                except PathNotAllowedError as e:
                    raise ValueError(str(e)) from e
                if not rel_n:
                    raise ValueError("root path cannot be empty")
                try:
                    d = assert_allowed_path(root, rel_n, prefixes)
                except PathNotAllowedError as e:
                    raise ValueError(str(e)) from e
                if not d.is_dir():
                    raise ValueError(f"not a directory: {rel_n}")
                roots_norm.append(rel_n)

            if not roots_norm:
                raise ValueError("no valid scan roots")

            scan_id = uuid.uuid4().hex[:10]
            self._current = DupScanState(
                scan_id=scan_id,
                phase=DupScanPhase.running,
                started_unix=time.time(),
            )
            self._progress = {"files_scanned": 0, "files_hashed": 0, "groups_found": 0}

            self._task = asyncio.create_task(
                self._run_thread_scan(
                    scan_id=scan_id,
                    archive_root=root,
                    prefixes=prefixes,
                    roots_norm=roots_norm,
                    include_video=include_video,
                    include_images=include_images,
                )
            )
        return scan_id

    async def _run_thread_scan(
        self,
        *,
        scan_id: str,
        archive_root: Path,
        prefixes: list[str],
        roots_norm: list[str],
        include_video: bool,
        include_images: bool,
    ) -> None:
        loop = asyncio.get_event_loop()

        def on_progress(fs: int, fh: int, gf: int) -> None:
            self._progress["files_scanned"] = fs
            self._progress["files_hashed"] = fh
            self._progress["groups_found"] = gf

        def work() -> tuple[list[DuplicateGroup], dict[str, int]]:
            return find_duplicate_groups(
                archive_root,
                prefixes,
                roots_norm,
                include_video=include_video,
                include_images=include_images,
                on_progress=on_progress,
            )

        t0 = time.time()
        try:
            groups, stats = await loop.run_in_executor(None, work)
        except Exception as e:
            logger.warning("duplicate scan %s failed: %s", scan_id, e)
            async with self._lock:
                if self._current and self._current.scan_id == scan_id:
                    self._current.phase = DupScanPhase.failed
                    self._current.ended_unix = time.time()
                    self._current.error = str(e)
            return

        elapsed = time.time() - t0
        gdicts = [
            {
                "group_id": g.group_id,
                "content_hash": g.content_hash,
                "total_size": g.total_size,
                "files": g.files,
            }
            for g in groups
        ]
        logger.info(
            "duplicate scan id=%s duration_s=%.2f groups=%s files_scanned=%s files_hashed=%s",
            scan_id,
            elapsed,
            stats.get("duplicate_groups", 0),
            stats.get("files_scanned", 0),
            stats.get("files_hashed", 0),
        )

        async with self._lock:
            if self._current and self._current.scan_id == scan_id:
                self._current.phase = DupScanPhase.success
                self._current.ended_unix = time.time()
                self._current.stats = stats
                self._current.groups = gdicts
                self._progress["files_scanned"] = stats.get("files_scanned", 0)
                self._progress["files_hashed"] = stats.get("files_hashed", 0)
                self._progress["groups_found"] = stats.get("duplicate_groups", 0)
