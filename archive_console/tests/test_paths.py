from pathlib import Path

import pytest

from app.paths import (
    PathNotAllowedError,
    assert_allowed_path,
    expand_allowlist_prefix,
    is_allowed,
    normalize_rel,
    resolve_under_root,
)


def test_normalize_rejects_dotdot():
    with pytest.raises(PathNotAllowedError):
        normalize_rel("..")
    with pytest.raises(PathNotAllowedError):
        normalize_rel("logs/../secret")


def test_resolve_stays_under_root(tmp_path: Path):
    root = tmp_path
    (root / "logs").mkdir()
    r = resolve_under_root(root, "logs/x")
    assert r == root / "logs" / "x"


def test_normalize_rejects_embedded_dotdot():
    with pytest.raises(PathNotAllowedError):
        normalize_rel("logs/foo/../../secret")


def test_allowlist_prefix(tmp_path: Path):
    root = tmp_path
    (root / "logs" / "a").mkdir(parents=True)
    (root / "evil").mkdir()
    allowed = ["logs"]
    assert is_allowed(root, root / "logs" / "a", allowed)
    assert not is_allowed(root, root / "evil", allowed)


def test_allowlist_nested_folder_name(tmp_path: Path):
    root = tmp_path
    nested = root / "playlists" / "Watch Later Archived"
    nested.mkdir(parents=True)
    f = nested / "clip.mp4"
    f.write_bytes(b"x")
    assert is_allowed(root, f, ["Watch Later Archived"])
    assert is_allowed(root, f, ["playlists"])
    assert is_allowed(root, f, ["playlists/Watch Later Archived"])
    assert not is_allowed(root, f, ["WL"])


def test_allowlist_nested_wl_folder(tmp_path: Path):
    root = tmp_path
    wl = root / "playlists" / "WL"
    wl.mkdir(parents=True)
    f = wl / "clip.mp4"
    f.write_bytes(b"x")
    assert is_allowed(root, f, ["WL"])
    assert is_allowed(root, f, ["playlists"])


def test_expand_allowlist_prefix_unique_nested(tmp_path: Path):
    root = tmp_path
    nested = root / "playlists" / "Watch Later Archived"
    nested.mkdir(parents=True)
    assert (
        expand_allowlist_prefix(root, "Watch Later Archived")
        == "playlists/Watch Later Archived"
    )
    assert expand_allowlist_prefix(root, "playlists") == "playlists"


def test_assert_allowed_path(tmp_path: Path):
    root = tmp_path
    (root / "videos" / "f.txt").parent.mkdir(parents=True)
    (root / "videos" / "f.txt").write_text("x", encoding="utf-8")
    p = assert_allowed_path(root, "videos/f.txt", ["videos", "logs"])
    assert p.name == "f.txt"


def test_assert_allowed_rejects_traversal_in_rel():
    root = Path("C:/fake").resolve()
    with pytest.raises(PathNotAllowedError):
        assert_allowed_path(root, "logs/../../../windows", ["logs"])
