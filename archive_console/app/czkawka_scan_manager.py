"""Single-flight Czkawka CLI scans (subprocess on host paths outside allowlist)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .czkawka_runner import (
    SCAN_MODES,
    build_czkawka_argv,
    czkawka_invocable,
    load_and_normalize_results,
    resolve_czkawka_bin,
    run_czkawka_subprocess,
    validate_host_directory,
)
from .download_output import state_allowed_prefixes
from .run_error_record import make_error_record, record_to_sidecar_or_global
from .settings import ConsoleState

logger = logging.getLogger(__name__)

_CZKAWKA_LOG_DIR = "_czkawka_scans"


class CzkScanPhase(str, Enum):
    idle = "idle"
    running = "running"
    success = "success"
    failed = "failed"


@dataclass
class CzkScanState:
    scan_id: str
    phase: CzkScanPhase
    started_unix: float
    mode: str
    directories: list[str]
    ended_unix: float | None = None
    error: str | None = None
    exit_code: int | None = None
    stderr_tail: str | None = None
    results: dict[str, Any] | None = None
    json_rel: str | None = None


@dataclass
class CzkawkaScanManager:
    get_state: Callable[[], ConsoleState]
    persist_state: Callable[[ConsoleState], None]
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _current: CzkScanState | None = None
    _task: asyncio.Task[None] | None = None
    _proc: subprocess.Popen[str] | None = None
    _stop_event: threading.Event = field(default_factory=threading.Event)

    @staticmethod
    def _kill_process(proc: subprocess.Popen[str] | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        with contextlib.suppress(OSError):
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)

    def status(self, *, include_results: bool = False) -> dict[str, Any]:
        c = self._current
        if c is None:
            return {"phase": CzkScanPhase.idle.value, "scan": None}
        scan: dict[str, Any] = {
            "scan_id": c.scan_id,
            "mode": c.mode,
            "directories": c.directories,
            "started_unix": c.started_unix,
            "ended_unix": c.ended_unix,
            "error": c.error,
            "exit_code": c.exit_code,
            "stderr_tail": c.stderr_tail,
            "json_rel": c.json_rel,
        }
        if include_results:
            scan["results"] = c.results
        elif c.results:
            scan["group_count"] = c.results.get("group_count", 0)
        return {"phase": c.phase.value, "scan": scan}

    def results(self) -> dict[str, Any]:
        c = self._current
        if c is None or c.phase != CzkScanPhase.success:
            return {"scan_id": None, "results": None}
        return {
            "scan_id": c.scan_id,
            "mode": c.mode,
            "results": c.results,
            "json_rel": c.json_rel,
        }

    def get_successful_scan(self, scan_id: str) -> CzkScanState | None:
        c = self._current
        if (
            c is None
            or c.phase != CzkScanPhase.success
            or c.scan_id != (scan_id or "").strip()
        ):
            return None
        return c

    def update_results(self, scan_id: str, results: dict[str, Any]) -> bool:
        c = self._current
        if c is None or c.scan_id != scan_id or c.phase != CzkScanPhase.success:
            return False
        c.results = results
        return True

    async def force_reset_running(self, reason: str = "force-reset") -> bool:
        async with self._lock:
            if self._current is None or self._current.phase != CzkScanPhase.running:
                return False
            scan_id = self._current.scan_id
            proc = self._proc
        self._stop_event.set()
        await asyncio.to_thread(self._kill_process, proc)
        async with self._lock:
            if (
                self._current
                and self._current.scan_id == scan_id
                and self._current.phase == CzkScanPhase.running
            ):
                self._current.phase = CzkScanPhase.failed
                self._current.ended_unix = time.time()
                self._current.error = reason[:500]
            self._proc = None
        logger.info("czkawka scan %s force reset: %s", scan_id, reason)
        return True

    async def start_scan(
        self,
        *,
        mode: str,
        directories: list[str],
        exclude_directories: list[str] | None = None,
        dup_method: str = "HASH",
        hash_type: str = "BLAKE3",
        minimal_file_size: int = 1024,
        extension_macros: list[str] | None = None,
        number_of_big_files: int = 50,
    ) -> str:
        mode_n = (mode or "dup").strip()
        if mode_n not in SCAN_MODES:
            raise ValueError(f"unsupported mode: {mode_n}")

        dirs: list[Path] = []
        for raw in directories:
            dirs.append(validate_host_directory(raw))
        if not dirs:
            raise ValueError("at least one scan directory is required")

        ex_dirs: list[Path] = []
        for raw in exclude_directories or []:
            if not (raw or "").strip():
                continue
            ex_dirs.append(validate_host_directory(raw))

        st = self.get_state()
        exe = resolve_czkawka_bin(st)
        if not czkawka_invocable(exe):
            raise ValueError(
                f"czkawka CLI not found ({exe!r}). Install from GitHub releases or set czkawka_exe in Settings."
            )

        async with self._lock:
            if self._current is not None and self._current.phase == CzkScanPhase.running:
                raise RuntimeError("A Czkawka scan is already running")

            scan_id = uuid.uuid4().hex[:10]
            self._stop_event.clear()
            self._current = CzkScanState(
                scan_id=scan_id,
                phase=CzkScanPhase.running,
                started_unix=time.time(),
                mode=mode_n,
                directories=[str(p) for p in dirs],
            )
            self._task = asyncio.create_task(
                self._run_scan(
                    scan_id=scan_id,
                    st=st,
                    exe=exe,
                    mode=mode_n,
                    directories=dirs,
                    exclude_directories=ex_dirs,
                    dup_method=dup_method,
                    hash_type=hash_type,
                    minimal_file_size=minimal_file_size,
                    extension_macros=extension_macros,
                    number_of_big_files=number_of_big_files,
                )
            )
        return scan_id

    async def _run_scan(
        self,
        *,
        scan_id: str,
        st: ConsoleState,
        exe: str,
        mode: str,
        directories: list[Path],
        exclude_directories: list[Path],
        dup_method: str,
        hash_type: str,
        minimal_file_size: int,
        extension_macros: list[str] | None,
        number_of_big_files: int,
    ) -> None:
        root = Path(st.archive_root).expanduser().resolve()
        log_dir = root / "logs" / _CZKAWKA_LOG_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        json_path = log_dir / f"scan_{scan_id}.json"
        json_rel = json_path.relative_to(root).as_posix()

        try:
            argv = build_czkawka_argv(
                exe=exe,
                mode=mode,  # type: ignore[arg-type]
                directories=directories,
                exclude_directories=exclude_directories,
                json_out=json_path,
                dup_method=dup_method,  # type: ignore[arg-type]
                hash_type=hash_type,  # type: ignore[arg-type]
                minimal_file_size=minimal_file_size,
                extension_macros=extension_macros,
                number_of_big_files=number_of_big_files,
            )
        except ValueError as e:
            async with self._lock:
                if self._current and self._current.scan_id == scan_id:
                    self._current.phase = CzkScanPhase.failed
                    self._current.ended_unix = time.time()
                    self._current.error = str(e)
            return

        loop = asyncio.get_event_loop()

        def work() -> tuple[int, str, str, bool]:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
            self._proc = proc
            stopped = False
            while proc.poll() is None:
                if self._stop_event.is_set():
                    stopped = True
                    CzkawkaScanManager._kill_process(proc)
                    break
                time.sleep(0.25)
            if stopped:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.communicate(timeout=2)
                return -1, "", "", True
            out, err = proc.communicate()
            code = proc.returncode if proc.returncode is not None else -1
            return code, out or "", err or "", False

        t0 = time.time()
        try:
            code, stdout, stderr, stopped = await loop.run_in_executor(None, work)
        except asyncio.CancelledError:
            proc = self._proc
            self._stop_event.set()
            await asyncio.to_thread(self._kill_process, proc)
            logger.info("czkawka scan %s canceled", scan_id)
            raise
        except Exception as e:
            logger.warning("czkawka scan %s failed: %s", scan_id, e)
            async with self._lock:
                if self._current and self._current.scan_id == scan_id:
                    self._current.phase = CzkScanPhase.failed
                    self._current.ended_unix = time.time()
                    self._current.error = str(e)
            self._record_error(st, scan_id, str(e), type(e).__name__)
            return
        finally:
            async with self._lock:
                self._proc = None

        if stopped or self._stop_event.is_set():
            async with self._lock:
                if self._current and self._current.scan_id == scan_id:
                    self._current.phase = CzkScanPhase.failed
                    self._current.ended_unix = time.time()
                    if not self._current.error:
                        self._current.error = "Stopped by operator"
                    self._current.exit_code = code
            logger.info("czkawka scan %s stopped (operator)", scan_id)
            return

        elapsed = time.time() - t0
        stderr_tail = (stderr or stdout or "").strip()[-800:]
        parsed = load_and_normalize_results(json_path, mode=mode)

        # czkawka exits non-zero when duplicates found unless -W; treat as success if JSON exists
        ok = json_path.is_file() and parsed.get("parse") not in ("missing_json", "json_error")
        if not ok and code != 0:
            err_msg = stderr_tail or f"czkawka exited with code {code}"
            async with self._lock:
                if self._current and self._current.scan_id == scan_id:
                    self._current.phase = CzkScanPhase.failed
                    self._current.ended_unix = time.time()
                    self._current.error = err_msg
                    self._current.exit_code = code
                    self._current.stderr_tail = stderr_tail
            self._record_error(st, scan_id, err_msg, "CzkawkaExit")
            return

        logger.info(
            "czkawka scan id=%s mode=%s duration_s=%.2f groups=%s code=%s",
            scan_id,
            mode,
            elapsed,
            parsed.get("group_count", 0),
            code,
        )

        async with self._lock:
            if not self._current or self._current.scan_id != scan_id:
                return
            if self._current.phase != CzkScanPhase.running:
                return
            self._current.phase = CzkScanPhase.success
            self._current.ended_unix = time.time()
            self._current.exit_code = code
            self._current.stderr_tail = stderr_tail or None
            self._current.results = parsed
            self._current.json_rel = json_rel

    def _record_error(
        self,
        st: ConsoleState,
        scan_id: str,
        message: str,
        exc_class: str,
    ) -> None:
        try:
            root = Path(st.archive_root).expanduser().resolve()
            rec = make_error_record(
                stage="czkawka",
                operation="czkawka_scan",
                message=message,
                severity="error",
                job_id=scan_id,
                technical={"exception_class": exc_class},
                retryable=True,
            )
            st2 = record_to_sidecar_or_global(
                archive_root=root,
                allowed_prefixes=state_allowed_prefixes(st),
                log_folder_rel=None,
                record=rec,
                state=st,
            )
            self.persist_state(st2)
        except Exception as persist_exc:
            logger.warning("czkawka scan %s: could not persist error: %s", scan_id, persist_exc)
