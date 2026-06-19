"""Gallery saved-source batch ordering (Twitter deprioritize)."""

from __future__ import annotations

import json
from pathlib import Path

from app.gallery_sources import iter_gallery_sources_for_run


def _write_sources(archive_root: Path, urls: list[str]) -> None:
    path = archive_root / "galleries" / "gallery_sources.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "id": f"id{i}",
            "url": u,
            "label": u,
            "last_run_unix": float(1000 - i),
        }
        for i, u in enumerate(urls)
    ]
    path.write_text(
        json.dumps({"schema_version": 1, "entries": entries}),
        encoding="utf-8",
    )


def test_iter_gallery_sources_deprioritize_twitter(tmp_path: Path) -> None:
    ar = tmp_path / "ar"
    ar.mkdir()
    _write_sources(
        ar,
        [
            "https://x.com/rzcos",
            "https://www.reddit.com/user/foo/submitted",
            "https://www.instagram.com/bar/",
        ],
    )
    ordered = iter_gallery_sources_for_run(ar, deprioritize_twitter=True)
    assert [u for u, _ in ordered] == [
        "https://www.reddit.com/user/foo/submitted",
        "https://www.instagram.com/bar/",
        "https://x.com/rzcos",
    ]


def test_iter_gallery_sources_default_keeps_sort(tmp_path: Path) -> None:
    ar = tmp_path / "ar"
    ar.mkdir()
    _write_sources(
        ar,
        [
            "https://x.com/rzcos",
            "https://www.reddit.com/user/foo/submitted",
        ],
    )
    ordered = iter_gallery_sources_for_run(ar, deprioritize_twitter=False)
    assert ordered[0][0] == "https://x.com/rzcos"
