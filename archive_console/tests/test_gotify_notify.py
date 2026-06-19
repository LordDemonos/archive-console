"""Gotify notifications for batch runs."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.settings as sm
from app.gotify_notify import (
    extract_failure_hints,
    format_gallery_batch_finished_message,
    format_run_finished_message,
    format_run_started_message,
    notify_run_finished,
    send_gotify_message,
    should_notify,
)
from app.run_manager import RunPhase, RunState
from app.settings import ConsoleState, normalize_gotify_base_url as norm_url


def test_validate_gotify_app_token_rejects_url() -> None:
    from app.settings import validate_gotify_app_token

    with pytest.raises(ValueError, match="not the server URL"):
        validate_gotify_app_token("http://192.168.1.234:8070")
    assert validate_gotify_app_token("AValidAppToken123") == "AValidAppToken123"


def test_normalize_gotify_base_url() -> None:
    assert norm_url("http://192.168.1.234:8070/") == "http://192.168.1.234:8070"
    assert norm_url("https://gotify.example.com:443") == "https://gotify.example.com:443"
    with pytest.raises(ValueError, match="http"):
        norm_url("ftp://x")
    with pytest.raises(ValueError, match="path"):
        norm_url("http://host/extra")


def test_should_notify_matrix() -> None:
    st = ConsoleState(
        archive_root="C:/ar",
        allowlisted_rel_prefixes=["logs"],
        gotify_enabled=True,
        gotify_base_url="http://127.0.0.1:8070",
        gotify_app_token="tok",
        gotify_notify_scheduled=True,
        gotify_notify_manual=False,
    )
    assert should_notify(st, trigger="scheduler", event="start", job="watch_later")
    assert should_notify(st, trigger="scheduler", event="start", job="galleries")
    assert not should_notify(st, trigger="manual", event="start", job="watch_later")
    assert not should_notify(st, trigger="manual", event="start", job="galleries")
    st2 = st.model_copy(update={"gotify_notify_on_start": False})
    assert not should_notify(st2, trigger="scheduler", event="start", job="watch_later")


def test_format_run_started_message() -> None:
    title, body = format_run_started_message(
        "watch_later",
        {"trigger": "scheduler", "schedule_frequency": "daily"},
        run_id="abc123",
        started_unix=1_700_000_000.0,
    )
    assert "watch_later" in title
    assert "**daily**" in body
    assert "**abc123**" in body


def test_format_run_finished_with_stats() -> None:
    finished = RunState(
        run_id="x",
        job="watch_later",
        phase=RunPhase.success,
        pid=None,
        started_unix=100.0,
        ended_unix=160.0,
        exit_code=0,
        run_meta={"trigger": "scheduler", "schedule_frequency": "daily"},
    )
    entry = {
        "run_stats": {"tried": 10, "saved": 3, "ok": 8, "fail": 2},
        "log_folder_rel": "logs/archive_run_test",
    }
    title, body = format_run_finished_message(finished, entry, failure_hints=None)
    assert "finished" in title
    assert "**Attempted:** 10" in body
    assert "`logs/archive_run_test`" in body


def test_extract_failure_hints_cookie(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    log_dir = root / "logs" / "run1"
    log_dir.mkdir(parents=True)
    (log_dir / "run.log").write_text(
        "line\n[archive] pause — cookie-auth issue detected\n",
        encoding="utf-8",
    )
    hints = extract_failure_hints(
        root,
        log_folder_rel="logs/run1",
        failure_detail=None,
        run_stats={"tried": 5, "ok": 0, "fail": 5, "saved": 0},
    )
    assert hints is not None
    assert "cookies.txt" in hints


@patch("app.gotify_notify.urllib.request.urlopen")
def test_send_gotify_payload(mock_urlopen: MagicMock) -> None:
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp

    st = ConsoleState(
        archive_root="C:/ar",
        allowlisted_rel_prefixes=["logs"],
        gotify_enabled=True,
        gotify_base_url="http://127.0.0.1:8070",
        gotify_app_token="secret",
    )
    assert send_gotify_message(st, title="T", message="**bold**") is True
    req = mock_urlopen.call_args[0][0]
    assert req.full_url.startswith("http://127.0.0.1:8070/message?token=")
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["markdown"] is True
    assert payload["priority"] == 5


@patch("app.gotify_notify.urllib.request.urlopen")
def test_send_gotify_failure_no_raise(mock_urlopen: MagicMock) -> None:
    mock_urlopen.side_effect = OSError("connection refused")
    st = ConsoleState(
        archive_root="C:/ar",
        allowlisted_rel_prefixes=["logs"],
        gotify_enabled=True,
        gotify_base_url="http://127.0.0.1:8070",
        gotify_app_token="secret",
    )
    assert send_gotify_message(st, title="T", message="M") is False


def test_format_gallery_batch_finished_message() -> None:
    results = [
        {
            "index": 1,
            "label": "r/pics",
            "phase": "success",
            "exit_code": 0,
            "started_unix": 100.0,
            "ended_unix": 200.0,
            "run_stats": {"tried": 5, "saved": 2, "ok": 4, "fail": 1},
        },
        {
            "index": 2,
            "label": "x.com/user",
            "phase": "success",
            "exit_code": 0,
            "started_unix": 200.0,
            "ended_unix": 300.0,
            "run_stats": {"tried": 1, "saved": 0, "ok": 1, "fail": 0},
            "failure_detail": "wall-clock limit",
        },
    ]
    title, body = format_gallery_batch_finished_message(
        results,
        {"trigger": "scheduler", "schedule_frequency": "weekly", "batch_total": 2},
    )
    assert "galleries batch" in title
    assert "**2/2**" in body
    assert "2 saved" in body
    assert "r/pics" in body
    assert "x.com/user" in body


def test_format_run_started_gallery_source() -> None:
    title, body = format_run_started_message(
        "galleries",
        {
            "trigger": "manual",
            "gallery_url": "https://www.reddit.com/r/pics/",
        },
        run_id="g1",
        started_unix=1_700_000_000.0,
    )
    assert "galleries" in title
    assert "**r/pics**" in body


@patch("app.gotify_notify.send_gotify_message")
def test_notify_run_finished_skips_gallery_batch_per_source(mock_send: MagicMock) -> None:
    st = ConsoleState(
        archive_root="C:/ar",
        allowlisted_rel_prefixes=["logs"],
        gotify_enabled=True,
        gotify_base_url="http://127.0.0.1:8070",
        gotify_app_token="tok",
    )
    finished = RunState(
        run_id="g1",
        job="galleries",
        phase=RunPhase.success,
        pid=None,
        started_unix=1.0,
        ended_unix=2.0,
        exit_code=0,
        run_meta={
            "trigger": "scheduler",
            "gallery_batch_index": 2,
            "gallery_batch_total": 5,
            "gallery_url": "https://www.reddit.com/r/pics/",
        },
    )
    notify_run_finished(st, finished, {"log_folder_rel": "logs/x"})
    mock_send.assert_not_called()


@patch("app.gotify_notify.send_gotify_message")
def test_notify_run_finished_scheduled_only(mock_send: MagicMock) -> None:
    st = ConsoleState(
        archive_root="C:/ar",
        allowlisted_rel_prefixes=["logs"],
        gotify_enabled=True,
        gotify_base_url="http://127.0.0.1:8070",
        gotify_app_token="tok",
        gotify_notify_manual=False,
    )
    finished = RunState(
        run_id="m1",
        job="watch_later",
        phase=RunPhase.success,
        pid=None,
        started_unix=1.0,
        ended_unix=2.0,
        exit_code=0,
        run_meta={"trigger": "manual"},
    )
    notify_run_finished(st, finished, {"log_folder_rel": "logs/x"})
    mock_send.assert_not_called()

    finished2 = RunState(
        run_id="m1",
        job="watch_later",
        phase=RunPhase.success,
        pid=None,
        started_unix=1.0,
        ended_unix=2.0,
        exit_code=0,
        run_meta={"trigger": "scheduler", "schedule_frequency": "daily"},
    )
    notify_run_finished(st, finished2, {"log_folder_rel": "logs/x"})
    mock_send.assert_called_once()


def test_run_manager_start_sets_run_meta_trigger() -> None:
    import asyncio
    from app.run_manager import RunManager

    mgr = RunManager(Path("."), Path("."))
    captured: dict = {}

    async def noop(_st):  # noqa: ANN001
        return None

    async def fake_run(*args, **kwargs):  # noqa: ANN001, ARG001
        captured["meta"] = dict(mgr.state.run_meta) if mgr.state else {}

    mgr._run_cmd = fake_run  # type: ignore[method-assign]

    async def run() -> None:
        with patch.object(Path, "is_file", return_value=True):
            await mgr.start(
                "watch_later",
                dry_run=True,
                skip_ytdlp_update=True,
                skip_pip_update=True,
                on_complete=noop,
                run_meta={"trigger": "scheduler", "schedule_id": "s1"},
            )

    asyncio.run(run())
    assert captured.get("meta", {}).get("trigger") == "scheduler"
    assert captured.get("meta", {}).get("schedule_id") == "s1"


def test_gotify_test_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ar = tmp_path / "archive"
    ar.mkdir()
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["logs"],
                "download_dirs": {
                    "watch_later": "",
                    "channels": "",
                    "videos": "",
                    "oneoff": "",
                    "galleries": "",
                },
                "features": {
                    "scheduler_enabled": False,
                    "notifications_stub": False,
                    "require_cookie_confirm_manual": False,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
                "gotify_enabled": True,
                "gotify_base_url": "http://127.0.0.1:8070",
                "gotify_app_token": "tok",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None  # noqa: SLF001
    with patch("app.gotify_notify.send_gotify_message", return_value=True):
        with TestClient(main.app) as client:
            r = client.post("/api/settings/gotify/test")
            assert r.status_code == 200
            assert r.json().get("ok") == "true"
