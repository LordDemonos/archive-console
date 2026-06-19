"""RunManager stop / force-reset and stream line formatting."""

from __future__ import annotations

import asyncio
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
