import pytest

from app.config_smoke import conf_syntax_smoke
from app.editor_backup import (
    BACKUP_DIR,
    backup_filename_stem,
    rotate_backups,
    write_backup_copy,
)
from app.editor_files import (
    COOKIES_TXT,
    EDITABLE_FILENAMES,
    parse_editor_filename,
    strip_blank_lines,
)
from app.paths import PathNotAllowedError


def test_parse_editor_filename_ok():
    assert parse_editor_filename("playlists_input.txt") == "playlists_input.txt"
    assert parse_editor_filename("yt-dlp.conf") == "yt-dlp.conf"
    assert parse_editor_filename("gallery-dl.conf") == "gallery-dl.conf"


def test_parse_editor_rejects():
    with pytest.raises(PathNotAllowedError):
        parse_editor_filename("../x")
    with pytest.raises(PathNotAllowedError):
        parse_editor_filename("secrets.env")
    with pytest.raises(PathNotAllowedError):
        parse_editor_filename("logs/x")


def test_strip_blank_lines():
    assert strip_blank_lines("a\n\nb\n  \nc") == "a\nb\nc\n"


def test_conf_smoke_null_byte():
    w = conf_syntax_smoke("a\n\0\n")
    assert any("Null" in x for x in w)


def test_backup_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.editor_backup.BACKUP_DIR", tmp_path / "backups")
    src = tmp_path / "playlists_input.txt"
    src.write_text("old", encoding="utf-8")
    p = write_backup_copy(src, "playlists_input.txt", max_keep=5)
    assert p is not None
    assert p.read_text() == "old"


def test_backup_rotation_deletes_old(tmp_path, monkeypatch):
    import time

    bdir = tmp_path / "backups"
    monkeypatch.setattr("app.editor_backup.BACKUP_DIR", bdir)
    bdir.mkdir()
    stem = backup_filename_stem("x.txt")
    for i in range(5):
        (bdir / f"{stem}.old{i}.bak").write_text(str(i), encoding="utf-8")
        time.sleep(0.02)
    rotate_backups(stem, max_keep=2)
    remaining = list(bdir.glob(f"{stem}.*.bak"))
    assert len(remaining) == 2


def test_editable_set_includes_cookies():
    assert COOKIES_TXT in EDITABLE_FILENAMES


def test_editable_set_includes_gallery_dl_conf():
    assert "gallery-dl.conf" in EDITABLE_FILENAMES
