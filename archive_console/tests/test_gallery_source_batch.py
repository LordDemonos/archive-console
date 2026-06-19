"""Gallery saved-sources batch scheduling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.gallery_source_batch import (
    GALLERY_SOURCES_SCHEDULE_ID,
    GALLERY_SOURCES_SCHEDULE_JOB,
    _reset_batch,
    continue_gallery_source_batch_if_any,
    gallery_batch_active,
    start_gallery_sources_batch,
    stop_gallery_source_batch_after_user_cancel,
)
from app.gallery_sources import upsert_gallery_source
from app.run_manager import RunPhase, RunState


@pytest.fixture(autouse=True)
def _clear_batch() -> None:
    _reset_batch()


@pytest.fixture()
def batch_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "logs").mkdir()
    (root / "galleries").mkdir()
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    st.allowlisted_rel_prefixes = ["logs", "galleries"]
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_gallery_sources_schedule_crud(batch_client: TestClient) -> None:
    r = batch_client.get("/api/galleries/sources/schedule")
    assert r.status_code == 200
    assert r.json().get("schedule") is None
    assert r.json().get("scheduled_max_run_sec") == 7200

    r2 = batch_client.post(
        "/api/galleries/sources/schedule",
        json={
            "enabled": True,
            "frequency": "daily",
            "hour": 3,
            "minute": 15,
            "scheduled_max_run_sec": 3600,
        },
    )
    assert r2.status_code == 200
    sch = r2.json().get("schedule")
    assert sch["job"] == GALLERY_SOURCES_SCHEDULE_JOB
    assert sch["id"] == GALLERY_SOURCES_SCHEDULE_ID
    assert sch["enabled"] is True
    assert sch["hour"] == 3
    assert r2.json().get("scheduled_max_run_sec") == 3600

    r3 = batch_client.get("/api/galleries/sources/schedule")
    assert r3.json().get("scheduled_max_run_sec") == 3600


def test_settings_schedules_accepts_gallery_sources(batch_client: TestClient) -> None:
    r = batch_client.post(
        "/api/settings/schedules",
        json={
            "schedules": [
                {
                    "id": "x",
                    "job": GALLERY_SOURCES_SCHEDULE_JOB,
                    "frequency": "weekly",
                    "day_of_week": 6,
                    "hour": 2,
                    "minute": 0,
                    "enabled": True,
                }
            ]
        },
    )
    assert r.status_code == 200


def test_start_gallery_sources_batch_queues(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "galleries").mkdir()
    upsert_gallery_source(root, "https://www.reddit.com/r/pics/", touch_only=True)
    upsert_gallery_source(root, "https://www.reddit.com/r/earthporn/", touch_only=True)

    from app.settings import ConsoleState, GalleryBatchRunSettings

    st = ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["galleries", "logs"],
        gallery_batch_run=GalleryBatchRunSettings(scheduled_max_run_sec=1800),
    )

    mgr = MagicMock()
    mgr.start = AsyncMock(
        return_value=RunState(
            run_id="r1",
            job="galleries",
            phase=RunPhase.running,
            pid=1,
            started_unix=1.0,
        )
    )

    on_complete = AsyncMock()

    async def _run() -> None:
        started = await start_gallery_sources_batch(
            mgr,
            on_complete,
            st=st,
            schedule_id="sch1",
            trigger="scheduler",
        )
        assert started is True
        assert gallery_batch_active()
        mgr.start.assert_awaited_once()
        call_kw = mgr.start.call_args.kwargs
        assert "reddit.com/r/" in call_kw["extra_env"]["ARCHIVE_GALLERY_URL"]
        assert call_kw["extra_env"]["ARCHIVE_GALLERY_MAX_RUN_SEC"] == "1800"

    asyncio.run(_run())


def test_continue_batch_starts_next(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "galleries").mkdir()
    upsert_gallery_source(root, "https://www.reddit.com/r/a/", touch_only=True)
    upsert_gallery_source(root, "https://www.reddit.com/r/b/", touch_only=True)

    from app.settings import ConsoleState

    st = ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["galleries", "logs"],
    )
    monkeypatch.setattr("app.gallery_source_batch.load_state", lambda: st)

    mgr = MagicMock()
    mgr.start = AsyncMock(
        return_value=RunState(
            run_id="r1",
            job="galleries",
            phase=RunPhase.running,
            pid=1,
            started_unix=1.0,
        )
    )
    mgr.status = AsyncMock(return_value={"phase": "success", "run": None})

    on_complete = AsyncMock()

    async def _run() -> None:
        await start_gallery_sources_batch(mgr, on_complete, st=st)
        finished = RunState(
            run_id="r1",
            job="galleries",
            phase=RunPhase.success,
            pid=1,
            started_unix=1.0,
            ended_unix=2.0,
            exit_code=0,
            run_meta={"gallery_batch_total": 2, "gallery_batch_index": 1},
        )
        await continue_gallery_source_batch_if_any(
            mgr, on_complete, finished=finished
        )
        assert mgr.start.await_count == 2

    asyncio.run(_run())


def test_cancel_batch_does_not_start_next(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    (root / "galleries").mkdir()
    upsert_gallery_source(root, "https://www.reddit.com/r/a/", touch_only=True)
    upsert_gallery_source(root, "https://www.reddit.com/r/b/", touch_only=True)

    from app.settings import ConsoleState

    st = ConsoleState(
        archive_root=str(root),
        allowlisted_rel_prefixes=["galleries", "logs"],
    )
    monkeypatch.setattr("app.gallery_source_batch.load_state", lambda: st)

    mgr = MagicMock()
    mgr.start = AsyncMock(
        return_value=RunState(
            run_id="r1",
            job="galleries",
            phase=RunPhase.running,
            pid=1,
            started_unix=1.0,
        )
    )
    mgr.status = AsyncMock(return_value={"phase": "canceled", "run": None})

    on_complete = AsyncMock()

    async def _run() -> None:
        await start_gallery_sources_batch(mgr, on_complete, st=st)
        assert gallery_batch_active()
        canceled = RunState(
            run_id="r1",
            job="galleries",
            phase=RunPhase.canceled,
            pid=1,
            started_unix=1.0,
            ended_unix=2.0,
            exit_code=-1,
            run_meta={"gallery_batch_total": 2, "gallery_batch_index": 1},
        )
        await stop_gallery_source_batch_after_user_cancel(canceled)
        assert not gallery_batch_active()
        await continue_gallery_source_batch_if_any(
            mgr, on_complete, finished=canceled
        )
        assert mgr.start.await_count == 1

    asyncio.run(_run())


def test_scheduler_enabled_patch(batch_client: TestClient) -> None:
    r = batch_client.post(
        "/api/settings",
        json={"scheduler_enabled": True},
    )
    assert r.status_code == 200
    j = batch_client.get("/api/settings").json()
    assert j.get("features", {}).get("scheduler_enabled") is True


def test_settings_includes_schedule_jobs(batch_client: TestClient) -> None:
    r = batch_client.get("/api/settings")
    assert r.status_code == 200
    jobs = r.json().get("schedule_jobs") or []
    assert GALLERY_SOURCES_SCHEDULE_JOB in jobs
