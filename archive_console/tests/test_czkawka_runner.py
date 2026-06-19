"""Czkawka CLI runner helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.czkawka_runner import (
    build_czkawka_argv,
    normalize_dup_json,
    validate_host_directory,
)


def test_normalize_dup_json_groups() -> None:
    raw = {
        "1024": [
            [
                {"path": "/a.mp4", "size": 1024, "hash": "abc", "modified_date": 1},
                {"path": "/b.mp4", "size": 1024, "hash": "abc", "modified_date": 2},
            ]
        ]
    }
    out = normalize_dup_json(raw)
    assert out["group_count"] == 1
    assert len(out["groups"][0]["files"]) == 2


def test_build_czkawka_argv_dup(tmp_path: Path) -> None:
    d = tmp_path / "scan"
    d.mkdir()
    json_out = tmp_path / "out.json"
    argv = build_czkawka_argv(
        exe="czkawka_cli",
        mode="dup",
        directories=[d],
        exclude_directories=[],
        json_out=json_out,
        dup_method="HASH",
        hash_type="BLAKE3",
        minimal_file_size=1024,
        extension_macros=["VIDEO"],
    )
    assert argv[0] == "czkawka_cli"
    assert argv[1] == "dup"
    assert "-d" in argv and str(d) in argv
    assert "-s" in argv and "HASH" in argv
    assert "--pretty-file-to-save" in argv
    assert str(json_out) in argv
    assert "-D" not in argv


def test_validate_host_directory(tmp_path: Path) -> None:
    p = validate_host_directory(str(tmp_path))
    assert p.is_dir()


def test_validate_host_directory_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a directory"):
        validate_host_directory(str(tmp_path / "nope"))
