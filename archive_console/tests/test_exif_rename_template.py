"""ExifTool-based filename template rendering and date fallback."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app.exif_rename_template import (
    first_date_from_tags,
    normalize_image_size,
    parse_exif_datetime,
    render_exif_template,
)


def test_parse_exif_datetime_exif_format() -> None:
    d = parse_exif_datetime("2023:05:10 14:30:00")
    assert d == datetime(2023, 5, 10, 14, 30, 0)


def test_first_date_from_tags_fallback() -> None:
    tags = {
        "CreateDate": "2023:01:02 00:00:00",
    }
    dt = first_date_from_tags(tags)
    assert dt is not None
    assert dt.year == 2023 and dt.month == 1


def test_render_stem_and_model() -> None:
    tags = {"EXIF:Model": "Nikon Z5"}
    out, warns = render_exif_template(
        "{Stem}_",
        tags,
        pipeline_stem="orig",
    )
    assert out == "orig_"
    assert not warns


def test_render_datetime_format() -> None:
    tags = {"EXIF:DateTimeOriginal": "2024:03:01 10:00:00"}
    out, warns = render_exif_template(
        "{DateTimeOriginal:%Y%m%d}_x",
        tags,
        pipeline_stem="",
    )
    assert out == "20240301_x"
    assert not warns


def test_normalize_image_size() -> None:
    assert normalize_image_size("4032 3024") == "4032x3024"


def test_build_rename_exif_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.rename_pipeline import RenamePreviewOptions, build_rename_preview

    root = tmp_path

    (root / "photos").mkdir()
    jpg = root / "photos" / "old.jpg"
    jpg.write_bytes(b"\xff\xd8\xff")

    def fake_exif(fp, **kwargs):  # noqa: ANN001
        return (
            {
                "EXIF:DateTimeOriginal": "2023:07:15 08:00:00",
                "Model": "TestCam",
            },
            "",
            "",
        )

    monkeypatch.setattr("app.rename_pipeline.run_exiftool_json", fake_exif)

    opt = RenamePreviewOptions(
        use_deepl=False,
        use_exif=True,
        exif_template="{DateTimeOriginal:%Y%m%d}_{Model}",
        exif_missing_policy="skip",
    )
    result = build_rename_preview(
        archive_root=root,
        allowed_prefixes=["photos"],
        rels=["photos/old.jpg"],
        opt=opt,
        stored_api_key="",
        endpoint_mode="auto",
        source_lang="",
        target_lang="EN-US",
        max_files=50,
        exiftool_exe="exiftool",
        exiftool_timeout_sec=30.0,
    )
    assert result["operation"] == "apply_exif_template"
    rows = result["rows"]
    assert len(rows) == 1
    assert rows[0]["status"] in ("ok", "warn")
    assert rows[0]["proposed_basename"] == "20230715_TestCam.jpg"
    assert "TestCam" in (rows[0].get("tags_preview") or "")
