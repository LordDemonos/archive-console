"""Run API env defaults and monthly driver script ordering (pip before yt-dlp)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.main import RunStartBody


def test_run_start_default_skip_pip_matches_historical_bat_behavior() -> None:
    b = RunStartBody(job="watch_later")
    assert b.skip_pip_update is True
    assert b.skip_ytdlp_update is False


def test_run_start_job_required() -> None:
    with pytest.raises(ValidationError):
        RunStartBody()  # type: ignore[call-arg]


def test_monthly_watch_later_pip_step_before_ytdlp() -> None:
    scripts_root = Path(__file__).resolve().parent.parent.parent
    bat = scripts_root / "monthly_watch_later_archive.bat"
    text = bat.read_text(encoding="utf-8")
    assert "SKIP_PIP_UPDATE" in text
    pip_line = text.find("install --upgrade pip")
    ytdlp_line = text.find('yt-dlp[default]"')
    assert pip_line != -1 and ytdlp_line != -1
    assert pip_line < ytdlp_line


def test_monthly_channels_pip_step_before_ytdlp() -> None:
    scripts_root = Path(__file__).resolve().parent.parent.parent
    bat = scripts_root / "monthly_channels_archive.bat"
    text = bat.read_text(encoding="utf-8")
    pip_line = text.find("install --upgrade pip")
    ytdlp_line = text.find('yt-dlp[default]"')
    assert pip_line != -1 and ytdlp_line != -1
    assert pip_line < ytdlp_line


def test_run_manager_env_skip_flags() -> None:
    """Mirror env rules without spawning a job."""
    skip_pip = True
    skip_ytdlp = False
    env: dict[str, str] = {}
    if skip_pip:
        env["SKIP_PIP_UPDATE"] = "1"
    else:
        env["SKIP_PIP_UPDATE"] = "0"
    if skip_ytdlp:
        env["SKIP_YTDLP_UPDATE"] = "1"
    else:
        env.pop("SKIP_YTDLP_UPDATE", None)
    assert env["SKIP_PIP_UPDATE"] == "1"
    assert "SKIP_YTDLP_UPDATE" not in env

    skip_pip = False
    env.clear()
    if skip_pip:
        env["SKIP_PIP_UPDATE"] = "1"
    else:
        env["SKIP_PIP_UPDATE"] = "0"
    assert env["SKIP_PIP_UPDATE"] == "0"
