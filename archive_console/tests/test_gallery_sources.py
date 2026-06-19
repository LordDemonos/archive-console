"""Gallery source URL registry (galleries/gallery_sources.json)."""

from __future__ import annotations

from pathlib import Path

from app.gallery_sources import (
    gallery_source_label,
    gallery_sources_json_path,
    gallery_sources_txt_path,
    list_gallery_sources_for_api,
    load_gallery_sources,
    record_gallery_source_after_run,
    remove_gallery_sources,
    upsert_gallery_source,
)


def test_gallery_source_label_subreddit() -> None:
    assert gallery_source_label("https://www.reddit.com/r/pics/") == "r/pics"


def test_gallery_source_label_user() -> None:
    u = "https://old.reddit.com/user/foo"
    assert gallery_source_label(u) == "u/foo"


def test_upsert_and_list_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    row = upsert_gallery_source(
        root,
        "https://www.reddit.com/r/test/",
        run_id="abc",
        exit_code=0,
        started_unix=1000.0,
    )
    assert row["label"] == "r/test"
    assert row["run_count"] == 1
    assert row["last_run_id"] == "abc"
    assert gallery_sources_json_path(root).is_file()
    assert gallery_sources_txt_path(root).is_file()
    assert "reddit.com/r/test" in gallery_sources_txt_path(root).read_text(encoding="utf-8")

    row2 = upsert_gallery_source(
        root,
        "https://www.reddit.com/r/test/",
        run_id="def",
        exit_code=4,
        started_unix=2000.0,
    )
    assert row2["run_count"] == 2
    assert row2["last_exit_code"] == 4

    api = list_gallery_sources_for_api(root)
    assert len(api["entries"]) == 1


def test_touch_only_add_without_run(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    row = upsert_gallery_source(
        root,
        "https://www.reddit.com/r/newsub/",
        touch_only=True,
    )
    assert row["run_count"] == 0
    assert row["last_run_unix"] is None


def test_remove_sources(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    row = upsert_gallery_source(root, "https://www.reddit.com/r/a/", touch_only=True)
    assert remove_gallery_sources(root, [row["id"]]) == 1
    assert load_gallery_sources(root)["entries"] == []


def test_gallery_source_display_url_strips_submitted() -> None:
    from app.gallery_sources import gallery_source_display_url

    assert (
        gallery_source_display_url(
            "https://www.reddit.com/user/miss_rachelann/submitted/"
        )
        == "https://www.reddit.com/user/miss_rachelann"
    )
    assert (
        gallery_source_display_url("https://www.reddit.com/r/pics/")
        == "https://www.reddit.com/r/pics/"
    )


def test_list_api_includes_url_display(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    upsert_gallery_source(
        root,
        "https://www.reddit.com/user/foo/submitted/",
        touch_only=True,
    )
    entries = list_gallery_sources_for_api(root)["entries"]
    assert entries[0]["url_display"] == "https://www.reddit.com/user/foo"


def test_upsert_stores_url_input_when_user_profile_normalized(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    raw = "https://www.reddit.com/user/foo"
    row = upsert_gallery_source(
        root,
        "https://www.reddit.com/user/foo/submitted/",
        url_input=raw,
        touch_only=True,
    )
    assert row["url_input"] == raw
    assert row["url"].rstrip("/").endswith("/submitted")


def test_record_gallery_source_after_run_skips_failed(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.run_manager import RunPhase

    root = tmp_path / "archive"
    root.mkdir()
    failed = SimpleNamespace(
        job="galleries",
        dry_run=False,
        phase=RunPhase.failed,
        exit_code=1,
        run_id="x1",
        started_unix=1.0,
        run_meta={"gallery_url": "https://www.reddit.com/r/test/"},
    )
    record_gallery_source_after_run(root, failed)
    assert load_gallery_sources(root)["entries"] == []


def test_record_gallery_source_after_run_on_success(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from app.run_manager import RunPhase

    root = tmp_path / "archive"
    root.mkdir()
    ok = SimpleNamespace(
        job="galleries",
        dry_run=False,
        phase=RunPhase.success,
        exit_code=0,
        run_id="x2",
        started_unix=2.0,
        run_meta={
            "gallery_url": "https://www.reddit.com/user/foo/submitted/",
            "gallery_url_input": "https://www.reddit.com/user/foo",
        },
    )
    record_gallery_source_after_run(root, ok)
    entries = load_gallery_sources(root)["entries"]
    assert len(entries) == 1
    assert entries[0]["run_count"] == 1
    assert entries[0]["url_input"] == "https://www.reddit.com/user/foo"
