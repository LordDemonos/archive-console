from pathlib import Path

import pytest
from fastapi import HTTPException

from app.file_serve import (
    assert_reports_file_not_sensitive,
    media_type_for_path,
)


def test_media_type_html():
    assert media_type_for_path(Path("x.html")) == "text/html; charset=utf-8"


def test_media_type_video():
    assert media_type_for_path(Path("a.mp4")) == "video/mp4"
    assert media_type_for_path(Path("b.mkv")) == "video/x-matroska"


def test_media_type_unknown_is_octet():
    assert media_type_for_path(Path("a.bin")) == "application/octet-stream"


def test_cookies_blocked():
    with pytest.raises(HTTPException) as ei:
        assert_reports_file_not_sensitive(Path("/fake/cookies.txt"))
    assert ei.value.status_code == 403
