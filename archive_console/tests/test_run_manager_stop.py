"""RunManager stop / force-reset and stream line formatting."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock

from app.run_manager import RunBroadcaster, RunManager, RunPhase, _format_stream_line


def test_format_stream_line_collapses_reddit_wall() -> None:
    wall = ".theme-light,:root{--rem360:22.5rem}" + ("x" * 5000)
    wall += " You've been blocked by network security. File a ticket"
    line = f"[reddit][error] {wall}"
    out = _format_stream_line(line)
    assert len(out) < 600
    assert "block" in out.lower()


def test_force_reset_clears_running_state(tmp_path: Path) -> None:
    async def _run() -> None:
        mgr = RunManager(archive_root=tmp_path)
        on_complete = AsyncMock()
        mgr._on_complete = on_complete
        from app.run_manager import RunState

        mgr.state = RunState(
            run_id="abc123",
            job="galleries",
            phase=RunPhase.running,
            pid=None,
            started_unix=0.0,
        )
        ok = await mgr.force_reset_running("test")
        assert ok is True
        assert mgr.state is not None
        assert mgr.state.phase == RunPhase.canceled
        on_complete.assert_awaited_once()

    asyncio.run(_run())


def test_stop_without_pid_cancels_task(tmp_path: Path) -> None:
    async def _run() -> None:
        mgr = RunManager(archive_root=tmp_path, broadcaster=RunBroadcaster())
        started = asyncio.Event()

        async def slow_job() -> None:
            started.set()
            await asyncio.sleep(3600)

        mgr._on_complete = AsyncMock()
        from app.run_manager import RunState

        mgr.state = RunState(
            run_id="r1",
            job="galleries",
            phase=RunPhase.running,
            pid=None,
            started_unix=0.0,
        )
        mgr._task = asyncio.create_task(slow_job())
        await started.wait()
        await mgr.stop()
        assert mgr.state.phase == RunPhase.canceled

    asyncio.run(_run())


def test_stop_clears_running_when_task_already_cancelled(tmp_path: Path) -> None:
    """Regression: task done via CancelledError without _finish left phase=running."""

    async def _run() -> None:
        mgr = RunManager(archive_root=tmp_path, broadcaster=RunBroadcaster())
        mgr._on_complete = AsyncMock()

        async def hang() -> None:
            await asyncio.sleep(3600)

        from app.run_manager import RunState

        mgr.state = RunState(
            run_id="wl01",
            job="watch_later",
            phase=RunPhase.running,
            pid=None,
            started_unix=0.0,
        )
        task = asyncio.create_task(hang())
        mgr._task = task
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert mgr.state.phase == RunPhase.running

        mgr._kill_tracked_tree = AsyncMock()  # type: ignore[method-assign]
        await mgr.stop()
        assert mgr.state is not None
        assert mgr.state.phase == RunPhase.canceled

    asyncio.run(_run())


def test_await_process_finalizes_when_stdout_pipe_stalls(tmp_path: Path) -> None:
    """Process exit must clear phase=running even if stdout.readline never EOFs."""

    async def _run() -> None:
        mgr = RunManager(archive_root=tmp_path, broadcaster=RunBroadcaster())
        on_complete = AsyncMock()

        class _StuckStdout:
            async def readline(self) -> bytes:
                await asyncio.sleep(3600)
                return b""

        class _Proc:
            def __init__(self) -> None:
                self.stdout = _StuckStdout()
                self.returncode = 0

            async def wait(self) -> int:
                return 0

            def kill(self) -> None:
                return None

        from app.run_manager import RunState

        mgr.state = RunState(
            run_id="oo1",
            job="oneoff",
            phase=RunPhase.running,
            pid=1,
            started_unix=0.0,
        )
        await mgr._supervise_subprocess("oo1", "oneoff", _Proc(), on_complete)  # type: ignore[arg-type]
        assert mgr.state is not None
        assert mgr.state.phase == RunPhase.success
        assert mgr.state.exit_code == 0
        on_complete.assert_awaited_once()

    asyncio.run(_run())
