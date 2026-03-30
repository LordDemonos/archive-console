"""gallery-dl executable resolution (PATH + venv Scripts next to sys.executable)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.gallery_cli import (
    gallery_dl_exe_invocable,
    resolve_gallery_dl_exe,
)


def test_resolve_gallery_dl_explicit_wins() -> None:
    assert resolve_gallery_dl_exe("C:\\bin\\gd.exe") == "C:\\bin\\gd.exe"
    assert resolve_gallery_dl_exe(" /tmp/gd ") == "/tmp/gd"


def test_resolve_finds_exe_next_to_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    fake_py = scripts / "python.exe"
    fake_py.write_bytes(b"MZ\x00\x00")
    (scripts / "gallery-dl.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(fake_py))
    monkeypatch.setattr("app.gallery_cli.shutil.which", lambda _x: None)
    resolved = resolve_gallery_dl_exe(None)
    assert resolved.lower().endswith("gallery-dl.exe")
    assert Path(resolved).is_file()


def test_gallery_dl_exe_invocable_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "gallery-dl.exe"
    p.write_text("", encoding="utf-8")
    monkeypatch.setattr("app.gallery_cli.shutil.which", lambda _x: None)
    assert gallery_dl_exe_invocable(str(p)) is True


def test_gallery_dl_exe_invocable_bare_name_without_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.gallery_cli.shutil.which", lambda _x: None)
    assert gallery_dl_exe_invocable("gallery-dl") is False
