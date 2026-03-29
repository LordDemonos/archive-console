"""Windows Explorer argv: /select must combine with path (regression for Explorer noop)."""

from pathlib import Path

import pytest

from app.main import explorer_launch_argv


def test_explorer_launch_opens_directory(tmp_path: Path) -> None:
    exe = Path("C:/Windows/explorer.exe")
    d = tmp_path / "d"
    d.mkdir()
    argv = explorer_launch_argv(exe, d)
    assert argv[0] == str(exe)
    assert argv[1] == str(d.resolve())
    assert len(argv) == 2


def test_explorer_launch_select_joins_path(tmp_path: Path) -> None:
    exe = Path("C:/Windows/explorer.exe")
    f = tmp_path / "long_name_example.txt"
    f.write_text("x", encoding="utf-8")
    argv = explorer_launch_argv(exe, f)
    assert len(argv) == 2
    assert argv[0] == str(exe)
    assert argv[1].startswith("/select,")
    assert str(f.resolve()) in argv[1]
    assert argv[1].index("/select,") == 0


@pytest.mark.parametrize("name", ["unicode_文件.txt", "with space.log"])
def test_explorer_launch_select_contains_resolved_path(
    tmp_path: Path, name: str
) -> None:
    exe = Path("C:/Windows/explorer.exe")
    f = tmp_path / name
    f.write_bytes(b".")
    argv = explorer_launch_argv(exe, f)
    assert str(f.resolve()) in argv[1]
