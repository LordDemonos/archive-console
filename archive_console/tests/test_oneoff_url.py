"""YouTube URL normalization for one-off API/driver."""

from __future__ import annotations

import pytest

from app.oneoff_url import normalize_oneoff_youtube_url


def test_empty_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_oneoff_youtube_url("")


def test_watch_url_accepted() -> None:
    u = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert normalize_oneoff_youtube_url(u) == u


def test_youtu_be_accepted() -> None:
    assert normalize_oneoff_youtube_url("https://youtu.be/dQw4w9WgXcQ").startswith(
        "https://youtu.be/"
    )


def test_bare_id_line() -> None:
    assert (
        normalize_oneoff_youtube_url("youtube dQw4w9WgXcQ")
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


def test_non_youtube_rejected() -> None:
    with pytest.raises(ValueError, match="YouTube"):
        normalize_oneoff_youtube_url("https://example.com/video")
