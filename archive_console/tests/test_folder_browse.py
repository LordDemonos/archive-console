"""Folder browse helpers (UTF-8 path resolution)."""

from __future__ import annotations

from pathlib import Path

from app.folder_browse import _resolve_picked_paths


def test_resolve_picked_paths_unicode_lines(tmp_path: Path) -> None:
    media = tmp_path / "playlists" / "한글 제목.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"x")
    stdout = f"{media.resolve()}\n"
    got = _resolve_picked_paths(stdout)
    assert got == [str(media.resolve())]
