"""ExifTool subprocess wrapper: timeout coercion (subprocess requires numeric timeout)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.exiftool_read import (
    EXIFTOOL_DEFAULT_TIMEOUT_SEC,
    normalize_exiftool_timeout_sec,
    run_exiftool_json,
)


def test_normalize_exiftool_timeout_str_coerces() -> None:
    assert normalize_exiftool_timeout_sec("45") == 45.0
    assert normalize_exiftool_timeout_sec("60.5") == 60.5


def test_normalize_exiftool_timeout_invalid_uses_default() -> None:
    assert normalize_exiftool_timeout_sec(None) == EXIFTOOL_DEFAULT_TIMEOUT_SEC
    assert normalize_exiftool_timeout_sec("not-a-number") == EXIFTOOL_DEFAULT_TIMEOUT_SEC
    assert normalize_exiftool_timeout_sec(object()) == EXIFTOOL_DEFAULT_TIMEOUT_SEC


def test_normalize_exiftool_timeout_clamped() -> None:
    assert normalize_exiftool_timeout_sec(1.0) == 5.0
    assert normalize_exiftool_timeout_sec(9999.0) == 600.0


def test_run_exiftool_json_string_timeout_passes_float_to_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "x.jpg"
    p.write_bytes(b"\xff\xd8\xff")
    timeouts: list[float | None] = []

    def fake_run(*_a, **kw):  # noqa: ANN002
        timeouts.append(kw.get("timeout"))

        class R:
            returncode = 0
            stderr = ""
            stdout = '[{"EXIF:Model": "Cam"}]'

        return R()

    monkeypatch.setattr("app.exiftool_read.subprocess.run", fake_run)

    first, _err, err_msg = run_exiftool_json(
        p,
        exiftool_bin="exiftool",
        timeout_sec="42",
    )
    assert err_msg == ""
    assert isinstance(first, dict)
    assert timeouts == [42.0]
