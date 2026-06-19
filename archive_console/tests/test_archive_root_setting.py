"""Archive root validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import validate_archive_root_setting


def test_validate_archive_root_existing_dir(tmp_path: Path) -> None:
    assert validate_archive_root_setting(str(tmp_path)) == str(tmp_path.resolve())


def test_validate_archive_root_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        validate_archive_root_setting(str(tmp_path / "missing"))
