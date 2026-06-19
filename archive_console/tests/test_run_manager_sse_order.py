"""SSE event order: start must precede lines so the UI routes logs to the correct panel."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.run_manager import RunManager


def test_galleries_missing_driver_emits_start_then_line_then_end(tmp_path: Path) -> None:
    async def _run() -> None:
        root = tmp_path
        mgr = RunManager(archive_root=root)
        q = await mgr.broadcaster.subscribe()

        async def on_complete(_st):  # noqa: ANN001
            return None

        with pytest.raises(FileNotFoundError):
            await mgr.start(
                "galleries",
                dry_run=True,
                skip_ytdlp_update=True,
                skip_pip_update=True,
                on_complete=on_complete,
            )

        msgs: list[dict] = []
        while True:
            try:
                raw = q.get_nowait()
            except asyncio.QueueEmpty:
                break
            msgs.append(json.loads(raw))

        assert [m["type"] for m in msgs] == ["start", "line", "end"]
        assert msgs[0].get("job") == "galleries"
        assert "Missing driver" in (msgs[1].get("text") or "")

    asyncio.run(_run())


def test_galleries_python_run_emits_start_starting_line_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _run() -> None:
        root = tmp_path
        (root / "archive_gallery_run.py").write_text("# stub\n", encoding="utf-8")

        class FakeProc:
            pid = 4242

            @property
            def stdout(self):
                class _Out:
                    async def readline(self_inner) -> bytes:
                        return b""

                return _Out()

            async def wait(self) -> int:
                return 0

        async def fake_exec(*_a, **_kw):  # noqa: ANN002, ANN003
            return FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

        mgr = RunManager(archive_root=root)
        q = await mgr.broadcaster.subscribe()

        async def on_complete(_st):  # noqa: ANN001
            return None

        await mgr.start(
            "galleries",
            dry_run=True,
            skip_ytdlp_update=True,
            skip_pip_update=True,
            on_complete=on_complete,
        )
        task = mgr._task
        assert task is not None
        await task

        msgs: list[dict] = []
        while True:
            try:
                msgs.append(json.loads(q.get_nowait()))
            except asyncio.QueueEmpty:
                break

        types = [m["type"] for m in msgs]
        assert types[0] == "start"
        assert types[1] == "line"
        assert "gallery-dl" in (msgs[1].get("text") or "").lower()
        assert types[-1] == "end"

    asyncio.run(_run())
