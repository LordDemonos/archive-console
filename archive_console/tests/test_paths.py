from pathlib import Path

import pytest

from app.paths import (
    PathNotAllowedError,
    assert_allowed_path,
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
