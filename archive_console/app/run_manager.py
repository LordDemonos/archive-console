"""Single active subprocess; broadcast log lines to SSE subscribers."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from .latest_pointer import read_latest_run_folder_rel


JobName = Literal["watch_later", "channels", "videos"]


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


BATCH_NAMES: dict[JobName, str] = {
    "watch_later": "monthly_watch_later_archive.bat",
    "channels": "monthly_channels_archive.bat",
    "videos": "monthly_videos_archive.bat",
}


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
    ) -> RunState:
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
        bat = self.archive_root / BATCH_NAMES[job]
        if not bat.is_file():
            async with self._lock:
                if self.state:
                    self.state.phase = RunPhase.failed
                    self.state.exit_code = -1
                    self.state.ended_unix = time.time()
            await self.broadcaster.publish(
                {"type": "line", "text": f"[console] Missing batch: {bat}"}
            )
            await self.broadcaster.publish({"type": "end", "exit_code": -1})
            await on_complete(self.state)
            raise FileNotFoundError(str(bat))

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
        if extra_env:
            env.update({k: v for k, v in extra_env.items() if k and v})

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
        """User stop: only the current running job's PID (spawned by this manager)."""
        async with self._lock:
            st = self.state
            if st is None or st.phase != RunPhase.running:
                raise RuntimeError("No job is running")
            rid = st.run_id
            pid = st.pid
            if pid is None:
                raise RuntimeError("Job is still starting — try again in a moment")
            self._canceled_run_id = rid
            task = self._task
        await self._kill_tracked_tree(pid)
        if task:
            try:
                await asyncio.wait_for(task, timeout=45.0)
            except asyncio.TimeoutError:
                pass

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
            await self.broadcaster.publish(
                {"type": "line", "text": f"[console] Failed to spawn: {e}"}
            )
            async with self._lock:
                if self.state and self.state.run_id == run_id:
                    self.state.phase = RunPhase.failed
                    self.state.exit_code = -1
                    self.state.ended_unix = time.time()
            await self.broadcaster.publish({"type": "end", "exit_code": -1})
            st = self.state
            await on_complete(st)
            return

        async with self._lock:
            if self.state and self.state.run_id == run_id:
                self.state.pid = proc.pid

        assert proc.stdout is not None
        while True:
            line_b = await proc.stdout.readline()
            if not line_b:
                break
            text = line_b.decode("utf-8", errors="replace").rstrip("\r\n")
            await self.broadcaster.publish({"type": "line", "text": text})

        exit_code = await proc.wait()
        log_rel = read_latest_run_folder_rel(self.archive_root, job)

        async with self._lock:
            user_canceled = self._canceled_run_id == run_id
            if user_canceled:
                self._canceled_run_id = None
            if self.state and self.state.run_id == run_id:
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
        await on_complete(st)
