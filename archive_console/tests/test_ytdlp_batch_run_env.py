"""YouTube batch cookie-pause settings → process env."""

from app.download_output import extra_env_for_ytdlp_batch
from app.settings import YtdlpBatchRunSettings


def test_ytdlp_batch_run_env_pause_off_clears_vars() -> None:
    env = extra_env_for_ytdlp_batch(YtdlpBatchRunSettings())
    assert env["ARCHIVE_PAUSE_ON_COOKIE_ERROR"] == ""
    assert env["ARCHIVE_COOKIE_AUTH_POLL_SEC"] == ""


def test_ytdlp_batch_run_env_pause_on_sets_poll() -> None:
    env = extra_env_for_ytdlp_batch(
        YtdlpBatchRunSettings(pause_on_cookie_error=True, cookie_auth_poll_sec=30)
    )
    assert env == {
        "ARCHIVE_PAUSE_ON_COOKIE_ERROR": "1",
        "ARCHIVE_COOKIE_AUTH_POLL_SEC": "30",
    }


def test_ytdlp_batch_run_settings_poll_bounds() -> None:
    y = YtdlpBatchRunSettings(cookie_auth_poll_sec=15)
    assert y.cookie_auth_poll_sec == 15
