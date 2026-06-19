"""RipMe-style Reddit gallery-dl merge + archive path resolution."""

from __future__ import annotations

import json
from pathlib import Path

from app.gallery_reddit import (
    GALLERY_DL_SKIP_LINE_PREFIX,
    apply_reddit_archive_path_if_unset,
    build_effective_gallery_conf_for_galleries,
    count_gallery_dl_skip_lines,
    merge_reddit_ripme_into_conf,
    merge_social_layout_into_conf,
    reddit_archive_db_path,
)


def test_reddit_archive_db_path_under_galleries_root(tmp_path: Path) -> None:
    g = tmp_path / "galleries"
    g.mkdir()
    p = reddit_archive_db_path(g)
    assert p.parent.name == "_gallery_dl_data"
    assert p.name == "reddit_archive.sqlite3"
    assert p.resolve() == g.resolve() / "_gallery_dl_data" / "reddit_archive.sqlite3"


def test_merge_reddit_preserves_operator_overrides() -> None:
    disk = {"extractor": {"reddit": {"skip": False}}}
    out = merge_reddit_ripme_into_conf(disk)
    assert out["extractor"]["reddit"]["skip"] is False
    assert "directory" in out["extractor"]["reddit"]


def test_merge_reddit_default_images_only() -> None:
    out = merge_reddit_ripme_into_conf({})
    assert out["extractor"]["reddit"]["videos"] is False
    assert "image-filter" in out["extractor"]["reddit"]
    assert out["extractor"]["reddit"]["parent-directory"] is True


def test_merge_reddit_blank_image_filter_uses_default() -> None:
    disk = {"extractor": {"reddit": {"image-filter": "", "videos": False}}}
    out = merge_reddit_ripme_into_conf(disk)
    assert out["extractor"]["reddit"]["videos"] is False
    assert "jpg" in out["extractor"]["reddit"]["image-filter"]


def test_merge_reddit_videos_dash_when_set() -> None:
    disk = {"extractor": {"reddit": {"videos": "dash"}}}
    out = merge_reddit_ripme_into_conf(disk)
    assert out["extractor"]["reddit"]["videos"] == "dash"


def test_apply_archive_only_when_unset(tmp_path: Path) -> None:
    g = tmp_path / "out"
    g.mkdir()
    conf = {"extractor": {"reddit": {}}}
    out = apply_reddit_archive_path_if_unset(conf, g)
    assert "archive" in out["extractor"]["reddit"]
    assert str(reddit_archive_db_path(g)) == out["extractor"]["reddit"]["archive"]

    custom = {"extractor": {"reddit": {"archive": "/custom/db.sqlite"}}}
    out2 = apply_reddit_archive_path_if_unset(custom, g)
    assert out2["extractor"]["reddit"]["archive"] == "/custom/db.sqlite"


def test_build_effective_merges_disk_conf(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    gdir = root / "galleries"
    gdir.mkdir()
    (root / "gallery-dl.conf").write_text(
        json.dumps({"extractor": {"reddit": {"videos": "dash"}}}),
        encoding="utf-8",
    )
    eff = build_effective_gallery_conf_for_galleries(root, gdir)
    assert eff["extractor"]["reddit"]["videos"] == "dash"
    assert "reddit_sub_{subreddit}" in json.dumps(eff["extractor"]["reddit"]["directory"])
    assert str(reddit_archive_db_path(gdir)) == eff["extractor"]["reddit"]["archive"]


def test_merge_social_layout_instagram_twitter() -> None:
    disk = {
        "extractor": {
            "directory": ["{category}", "{subcategory}"],
            "instagram": {"cookies": "cookies/instagram.txt"},
            "twitter": {"directory": ["custom_{user[name]}"]},
        }
    }
    out = merge_social_layout_into_conf(disk)
    assert out["extractor"]["directory"] == ["{category}", "{subcategory}"]
    ig_dir = out["extractor"]["instagram"]["directory"]
    assert ig_dir[""] == ["instagram_{username}"]
    assert out["extractor"]["twitter"]["directory"] == ["custom_{user[name]}"]


def test_build_effective_applies_social_layout(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    gdir = root / "galleries"
    gdir.mkdir()
    (root / "gallery-dl.conf").write_text(
        json.dumps({"extractor": {"directory": ["{category}", "{subcategory}"]}}),
        encoding="utf-8",
    )
    eff = build_effective_gallery_conf_for_galleries(root, gdir)
    assert eff["extractor"]["instagram"]["directory"][""] == ["instagram_{username}"]
    assert eff["extractor"]["twitter"]["directory"] == ["twitter_{user[name]}"]


def test_build_effective_auto_wires_site_cookies(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    root.mkdir()
    gdir = root / "galleries"
    gdir.mkdir()
    (root / "cookies").mkdir()
    (root / "cookies" / "instagram.txt").write_text("# netscape", encoding="utf-8")
    (root / "gallery-dl.conf").write_text(
        json.dumps({"extractor": {"patreon": {"cookies": ""}}}),
        encoding="utf-8",
    )
    eff = build_effective_gallery_conf_for_galleries(root, gdir)
    assert eff["extractor"]["instagram"]["cookies"] == "cookies/instagram.txt"
    assert eff["extractor"]["patreon"].get("cookies") == ""


def test_count_skip_lines() -> None:
    text = "ok\n# ./a.jpg\n# ./b.jpg\n"
    assert count_gallery_dl_skip_lines(text) == 2
    assert GALLERY_DL_SKIP_LINE_PREFIX == "# "
