"""Single active subprocess; broadcast log lines to SSE subscribers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal

from .cookie_preflight import (
    CookiePreflightTimeoutError,
    await_extension_cookie_preflight,
    ytdlp_job_needs_cookies,
)
from .driver_python import resolve_driver_python_exe
from .gallery_cli import run_gallery_dl_pip_update
from .latest_pointer import read_latest_run_folder_rel

logger = logging.getLogger(__name__)

# SSE / browser log lines — gallery-dl Reddit block pages can exceed 100 KB on one line.
STREAM_LINE_MAX = 4000

JobName = Literal["watch_later", "channels", "videos", "oneoff", "galleries"]

MonthlyJobName = Literal["watch_later", "channels", "videos"]


class RunPhase(str, Enum):
    idle = "idle"
    running = "running"
    success = "success"
    failed = "failed"
    canceled = "canceled"


@dataclass
class RunState:
    run_id: str
    job: JobName
    phase: RunPhase
    pid: int | None
    started_unix: float
    ended_unix: float | None = None
    exit_code: int | None = None
    dry_run: bool = False
    skip_ytdlp_update: bool = False
    skip_pip_update: bool = True
    log_folder_rel: str | None = None
    # Set when the console fails before/during subprocess (spawn, missing driver).
    failure_detail: str | None = None
    # Galleries: ARCHIVE_GALLERY_URL for history / sources registry on complete.
    run_meta: dict[str, Any] = field(default_factory=dict)


BATCH_NAMES: dict[MonthlyJobName, str] = {
    "watch_later": "monthly_watch_later_archive.bat",
    "channels": "monthly_channels_archive.bat",
    "videos": "monthly_videos_archive.bat",
}


def _job_console_label(job: JobName) -> str:
    if job == "galleries":
        return "gallery-dl (archive driver)"
    if job == "oneoff":
        return "one-off download"
    return str(job)


def _format_stream_line(text: str) -> str:
    """Truncate or replace wall-of-HTML gallery-dl errors before SSE/UI."""
    from .gallery_util import (
        compact_gallery_dl_wall_message,
        summarize_gallery_dl_parse_error_detail,
    )

    t = text.rstrip("\r\n")
    err_idx = t.find("][error]")
    if err_idx != -1:
        prefix = t[: err_idx + len("][error]")]
        rest = t[err_idx + len("][error]") :].lstrip()
        hit = compact_gallery_dl_wall_message(rest)
        if hit is not None:
            return f"{prefix} {hit}"
        budget = max(80, STREAM_LINE_MAX - len(prefix) - 1)
        rest = summarize_gallery_dl_parse_error_detail(rest, max_len=budget)
        return f"{prefix} {rest}"
    if len(t) > STREAM_LINE_MAX:
        return t[: STREAM_LINE_MAX - 1] + "…"
    return t


def _argv_basename_summary(argv: list[str], limit: int = 8) -> str:
    """Short spawn summary for logs (basenames only, no full paths)."""
    parts: list[str] = []
    for a in argv[:limit]:
        try:
            parts.append(Path(a).name)
        except (TypeError, ValueError):
            parts.append("?")
    if len(argv) > limit:
        parts.append("…")
    return " ".join(parts)


class RunBroadcaster:
    def __init__(self) -> None:
        self._subs: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        async with self._lock:
            self._subs.append(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    async def publish(self, msg: dict[str, Any]) -> None:
        line = json.dumps(msg, ensure_ascii=False)
        async with self._lock:
            for q in self._subs:
                try:
                    q.put_nowait(line)
                except asyncio.QueueFull:
                    pass


@dataclass
class RunManager:
    archive_root: Path
    broadcaster: RunBroadcaster = field(default_factory=RunBroadcaster)
    state: RunState | None = None
    _task: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # run_id we are stopping — distinguishes user cancel from natural non-zero exit
    _canceled_run_id: str | None = None
    _on_complete: Callable[[RunState | None], Any] | None = None

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            if self.state is None:
                return {"phase": RunPhase.idle.value, "run": None}
            r = self.state
            return {
                "phase": r.phase.value,
                "run": {
                    "run_id": r.run_id,
                    "job": r.job,
                    "pid": r.pid,
                    "started_unix": r.started_unix,
                    "ended_unix": r.ended_unix,
                    "exit_code": r.exit_code,
                    "dry_run": r.dry_run,
                    "skip_ytdlp_update": r.skip_ytdlp_update,
                    "skip_pip_update": r.skip_pip_update,
                    "log_folder_rel": r.log_folder_rel,
                },
            }

    async def start(
        self,
        job: JobName,
        *,
        dry_run: bool,
        skip_ytdlp_update: bool,
        skip_pip_update: bool,
        on_complete,
        extra_env: dict[str, str] | None = None,
        run_meta: dict[str, Any] | None = None,
        preflight_via_extension: bool = False,
        preflight_wait_sec: float = 120,
    ) -> RunState:
        async with self._lock:
            if self.state is not None and self.state.phase == RunPhase.running:
                raise RuntimeError("A job is already running")

        if (
            not dry_run
            and preflight_via_extension
            and ytdlp_job_needs_cookies(job)
        ):
            ok, msg = await await_extension_cookie_preflight(
                self.archive_root,
                job=job,
                timeout_sec=preflight_wait_sec,
                broadcaster=self.broadcaster,
            )
            if not ok:
                raise CookiePreflightTimeoutError(msg)

        async with self._lock:
            if self.state is not None and self.state.phase == RunPhase.running:
                raise RuntimeError("A job is already running")
            run_id = uuid.uuid4().hex[:8]
            self.state = RunState(
                run_id=run_id,
                job=job,
                phase=RunPhase.running,
                pid=None,
                started_unix=time.time(),
                dry_run=dry_run,
                skip_ytdlp_update=skip_ytdlp_update,
                skip_pip_update=skip_pip_update,
            )

        env = os.environ.copy()
        env["ARCHIVE_CONSOLE_UNATTENDED"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        if dry_run:
            env["ARCHIVE_DRY_RUN"] = "1"
        else:
            env.pop("ARCHIVE_DRY_RUN", None)
        if skip_ytdlp_update:
            env["SKIP_YTDLP_UPDATE"] = "1"
        else:
            env.pop("SKIP_YTDLP_UPDATE", None)
        # SKIP_PIP_UPDATE=1 skip pip self-upgrade; explicit "0" when upgrading (sets bat policy before yt-dlp step)
        if skip_pip_update:
            env["SKIP_PIP_UPDATE"] = "1"
        else:
            env["SKIP_PIP_UPDATE"] = "0"
        _CONSOLE_CLEARABLE_ENV_KEYS = frozenset(
            {
                "ARCHIVE_PAUSE_ON_COOKIE_ERROR",
                "ARCHIVE_COOKIE_AUTH_POLL_SEC",
            }
        )
        if extra_env:
            for k, v in extra_env.items():
                if not k:
                    continue
                if v:
                    env[k] = v
                elif k in _CONSOLE_CLEARABLE_ENV_KEYS:
                    env.pop(k, None)
        run_meta_merged: dict[str, Any] = dict(run_meta or {})
        if "trigger" not in run_meta_merged:
            run_meta_merged["trigger"] = "manual"
        
        if job == "galleries" and extra_env:
            gurl = (extra_env.get("ARCHIVE_GALLERY_URL") or "").strip()
            if gurl:
                run_meta_merged["gallery_url"] = gurl
                gin = (extra_env.get("ARCHIVE_GALLERY_URL_INPUT") or "").strip()
                if gin and gin.rstrip("/") != gurl.rstrip("/"):
                    run_meta_merged["gallery_url_input"] = gin
                
                from .gallery_util import get_cookie_path_from_url
                cookie_path = get_cookie_path_from_url(gurl)
                if cookie_path:
                    env["ARCHIVE_COOKIE_FILE"] = cookie_path
                    run_meta_merged["cookie_file"] = cookie_path
                    logger.info("Selected cookie file: %s", cookie_path)

        if run_meta_merged:
            async with self._lock:
                if self.state:
                    self.state.run_meta = run_meta_merged

                if self.state:
                    self.state.run_meta = run_meta_merged

        self._on_complete = on_complete

        if job == "oneoff":
            script = self.archive_root / "archive_oneoff_run.py"
            if not script.is_file():
                async with self._lock:
                    if self.state:
                        self.state.phase = RunPhase.failed
                        self.state.exit_code = -1
                        self.state.ended_unix = time.time()
                        self.state.failure_detail = f"Missing driver script: {script.name}"
                await self.broadcaster.publish(
                    {
                        "type": "start",
                        "run_id": run_id,
                        "job": job,
                        "cmd": "(driver missing)",
                    }
                )
                await self.broadcaster.publish(
                    {"type": "line", "text": f"[console] Missing driver: {script}"}
                )
                await self.broadcaster.publish({"type": "end", "exit_code": -1})
                await on_complete(self.state)
                raise FileNotFoundError(str(script))
            from datetime import datetime, timezone

            log_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            py_exe = resolve_driver_python_exe(self.archive_root)
            self._task = asyncio.create_task(
                self._run_python(
                    run_id,
                    job,
                    [str(py_exe), "-u", str(script), log_stamp],
                    env,
                    on_complete,
                )
            )
            return self.state  # type: ignore[return-value]

        if job == "galleries":
            script = self.archive_root / "archive_gallery_run.py"
            if not script.is_file():
                async with self._lock:
                    if self.state:
                        self.state.phase = RunPhase.failed
                        self.state.exit_code = -1
                        self.state.ended_unix = time.time()
                        self.state.failure_detail = f"Missing driver script: {script.name}"
                await self.broadcaster.publish(
                    {
                        "type": "start",
                        "run_id": run_id,
                        "job": job,
                        "cmd": "(driver missing)",
                    }
                )
                await self.broadcaster.publish(
                    {"type": "line", "text": f"[console] Missing driver: {script}"}
                )
                await self.broadcaster.publish({"type": "end", "exit_code": -1})
                await on_complete(self.state)
                raise FileNotFoundError(str(script))
            from datetime import datetime, timezone

            log_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            py_exe = resolve_driver_python_exe(self.archive_root)
            self._task = asyncio.create_task(
                self._run_python(
                    run_id,
                    job,
                    [str(py_exe), "-u", str(script), log_stamp],
                    env,
                    on_complete,
                )
            )
            return self.state  # type: ignore[return-value]

        bat = self.archive_root / BATCH_NAMES[job]
        if not bat.is_file():
            async with self._lock:
                if self.state:
                    self.state.phase = RunPhase.failed
                    self.state.exit_code = -1
                    self.state.ended_unix = time.time()
                    self.state.failure_detail = f"Missing batch file: {bat.name}"
            await self.broadcaster.publish(
                {
                    "type": "start",
                    "run_id": run_id,
                    "job": job,
                    "cmd": "(batch missing)",
                }
            )
            await self.broadcaster.publish(
                {"type": "line", "text": f"[console] Missing batch: {bat}"}
            )
            await self.broadcaster.publish({"type": "end", "exit_code": -1})
            await on_complete(self.state)
            raise FileNotFoundError(str(bat))

        self._task = asyncio.create_task(
            self._run_cmd(run_id, job, bat, env, on_complete)
        )
        return self.state  # type: ignore[return-value]

    async def _kill_tracked_tree(self, pid: int) -> None:
        """Kill only the known root PID (cmd.exe for this job) and its children (Windows: /T)."""
        if pid <= 0:
            return
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    async def stop(self) -> None:
        """User stop: kill tracked PID tree, then finish or force-reset run state."""
        async with self._lock:
            st = self.state
            if st is None or st.phase != RunPhase.running:
                raise RuntimeError("No job is running")
            rid = st.run_id
            pid = st.pid
            self._canceled_run_id = rid
            task = self._task
        if pid is not None and pid > 0:
            try:
                await self._kill_tracked_tree(pid)
            except OSError as e:
                logger.warning("stop: kill pid=%s failed: %s", pid, e)
        elif task and not task.done():
            task.cancel()
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=15.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                await self._abort_running_task(rid, task)
            except Exception:
                logger.exception("stop: waiting for run task run_id=%s", rid)
                await self._abort_running_task(rid, task)
        async with self._lock:
            still_running = (
                self.state is not None
                and self.state.run_id == rid
                and self.state.phase == RunPhase.running
            )
        if still_running:
            await self._force_canceled(rid, reason="stop")

    async def force_reset_running(self, reason: str = "force-reset") -> bool:
        """Emergency recovery when stop/stream desync leaves phase=running."""
        async with self._lock:
            st = self.state
            if st is None or st.phase != RunPhase.running:
                return False
            rid = st.run_id
            pid = st.pid
            task = self._task
        if pid is not None and pid > 0:
            with contextlib.suppress(OSError):
                await self._kill_tracked_tree(pid)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(task, timeout=3.0)
        await self._force_canceled(rid, reason=reason)
        return True

    async def _abort_running_task(self, run_id: str, task: asyncio.Task | None) -> None:
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(task, timeout=3.0)
        await self._force_canceled(run_id, reason="stop-timeout")

    async def _force_canceled(self, run_id: str, *, reason: str) -> None:
        on_complete = self._on_complete
        st_out: RunState | None = None
        async with self._lock:
            if (
                self.state
                and self.state.run_id == run_id
                and self.state.phase == RunPhase.running
            ):
                self.state.phase = RunPhase.canceled
                self.state.exit_code = -1
                self.state.ended_unix = time.time()
                self.state.failure_detail = reason[:500]
                self._canceled_run_id = None
                st_out = self.state
        if st_out is None:
            return
        await self.broadcaster.publish(
            {"type": "end", "exit_code": -1, "canceled": True}
        )
        if on_complete:
            try:
                await on_complete(st_out)
            except Exception:
                logger.exception("on_complete after force cancel run_id=%s", run_id)

    async def _pip_update_gallery_dl(self) -> None:
        py = resolve_driver_python_exe(self.archive_root)
        await self.broadcaster.publish(
            {
                "type": "line",
                "text": "[console] Updating gallery-dl (pip install -U gallery-dl)…",
            }
        )
        rc, lines = await asyncio.to_thread(run_gallery_dl_pip_update, py)
        for line in lines[-40:]:
            await self.broadcaster.publish({"type": "line", "text": line})
        if rc == 0:
            await self.broadcaster.publish(
                {
                    "type": "line",
                    "text": "[console] gallery-dl pip update finished OK.",
                }
            )
        else:
            await self.broadcaster.publish(
                {
                    "type": "line",
                    "text": (
                        "[console] WARNING: gallery-dl pip update failed "
                        f"(exit {rc}); continuing with installed version."
                    ),
                }
            )

    async def _pump_stdout_lines(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while True:
            line_b = await proc.stdout.readline()
            if not line_b:
                break
            text = _format_stream_line(line_b.decode("utf-8", errors="replace"))
            await self.broadcaster.publish({"type": "line", "text": text})

    async def _await_process_and_stream(
        self, proc: asyncio.subprocess.Process
    ) -> int:
        """Wait for process exit without blocking forever on a stuck stdout pipe.

        On Windows, a child (ffmpeg/node/etc.) can keep the pipe write-end open
        after the tracked PID exits; readline() alone then never finishes and the
        UI stays phase=running forever even though the download already succeeded.
        """
        assert proc.stdout is not None
        pump = asyncio.create_task(self._pump_stdout_lines(proc))
        try:
            exit_code = await proc.wait()
        except asyncio.CancelledError:
            if not pump.done():
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pump
            raise
        if not pump.done():
            try:
                await asyncio.wait_for(pump, timeout=2.0)
            except asyncio.TimeoutError:
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pump
                await self.broadcaster.publish(
                    {
                        "type": "line",
                        "text": (
                            "[console] Warning: log stream stalled after process "
                            "exit; finalizing run anyway."
                        ),
                    }
                )
            except asyncio.CancelledError:
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pump
                raise
            except Exception:
                logger.warning(
                    "stdout pump failed after process exit", exc_info=True
                )
        else:
            with contextlib.suppress(asyncio.CancelledError):
                exc = pump.exception()
                if exc is not None:
                    logger.warning("stdout pump failed: %s", exc)
        return exit_code

    async def _supervise_subprocess(
        self,
        run_id: str,
        job: JobName,
        proc: asyncio.subprocess.Process,
        on_complete,
    ) -> None:
        try:
            exit_code = await self._await_process_and_stream(proc)
            await self._finish_run_task(run_id, job, exit_code, on_complete)
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
            await self._finish_run_task(run_id, job, -1, on_complete)
            raise
        except Exception as e:
            logger.exception("run task crashed job=%s run_id=%s", job, run_id)
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
            async with self._lock:
                if self.state and self.state.run_id == run_id:
                    self.state.failure_detail = f"Run monitor crashed: {e}"[:500]
            await self._finish_run_task(run_id, job, -1, on_complete)

    async def _run_python(
        self,
        run_id: str,
        job: JobName,
        argv: list[str],
        env: dict[str, str],
        on_complete,
    ) -> None:
        await self.broadcaster.publish(
            {
                "type": "start",
                "run_id": run_id,
                "job": job,
                "cmd": " ".join(argv),
            }
        )
        await self.broadcaster.publish(
            {
                "type": "line",
                "text": f"[console] Starting {_job_console_label(job)}…",
            }
        )
        if job == "galleries" and env.get("ARCHIVE_GALLERY_DL_UPDATE") == "1":
            await self._pip_update_gallery_dl()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(self.archive_root.resolve()),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            logger.warning(
                "subprocess spawn failed job=%s argv_summary=%s err=%s",
                job,
                _argv_basename_summary(list(argv)),
                e,
            )
            await self.broadcaster.publish(
                {"type": "line", "text": f"[console] Failed to spawn: {e}"}
            )
            async with self._lock:
                if self.state and self.state.run_id == run_id:
                    self.state.phase = RunPhase.failed
                    self.state.exit_code = -1
                    self.state.ended_unix = time.time()
                    self.state.failure_detail = f"Subprocess spawn failed: {e}"
            await self.broadcaster.publish({"type": "end", "exit_code": -1})
            st = self.state
            await on_complete(st)
            return

        async with self._lock:
            if self.state and self.state.run_id == run_id:
                self.state.pid = proc.pid

        await self._supervise_subprocess(run_id, job, proc, on_complete)

    async def _finish_run_task(
        self,
        run_id: str,
        job: JobName,
        exit_code: int,
        on_complete,
    ) -> None:
        log_rel = read_latest_run_folder_rel(self.archive_root, job)

        async with self._lock:
            user_canceled = self._canceled_run_id == run_id
            if user_canceled:
                self._canceled_run_id = None
            if self.state and self.state.run_id == run_id:
                if self.state.phase != RunPhase.running:
                    return
                self.state.exit_code = exit_code
                self.state.ended_unix = time.time()
                if user_canceled:
                    self.state.phase = RunPhase.canceled
                elif exit_code == 0:
                    self.state.phase = RunPhase.success
                else:
                    self.state.phase = RunPhase.failed
                self.state.log_folder_rel = log_rel

        await self.broadcaster.publish(
            {
                "type": "end",
                "exit_code": exit_code,
                "canceled": user_canceled,
            }
        )
        st = self.state
        if on_complete:
            await on_complete(st)

    async def _run_cmd(
        self,
        run_id: str,
        job: JobName,
        bat: Path,
        env: dict[str, str],
        on_complete,
    ) -> None:
        await self.broadcaster.publish(
            {
                "type": "start",
                "run_id": run_id,
                "job": job,
                "cmd": str(bat),
            }
        )
        await self.broadcaster.publish(
            {
                "type": "line",
                "text": f"[console] Starting monthly {job} batch…",
            }
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                os.environ.get("ComSpec", "cmd.exe"),
                "/c",
                str(bat),
                cwd=str(self.archive_root.resolve()),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            logger.warning(
                "batch spawn failed job=%s bat=%s err=%s",
                job,
                bat.name,
                e,
            )
            await self.broadcaster.publish(
                {"type": "line", "text": f"[console] Failed to spawn: {e}"}
            )
            async with self._lock:
                if self.state and self.state.run_id == run_id:
                    self.state.phase = RunPhase.failed
                    self.state.exit_code = -1
                    self.state.ended_unix = time.time()
                    self.state.failure_detail = f"Batch spawn failed: {e}"
            await self.broadcaster.publish({"type": "end", "exit_code": -1})
            st = self.state
            await on_complete(st)
            return

        async with self._lock:
            if self.state and self.state.run_id == run_id:
                self.state.pid = proc.pid

        await self._supervise_subprocess(run_id, job, proc, on_complete)
