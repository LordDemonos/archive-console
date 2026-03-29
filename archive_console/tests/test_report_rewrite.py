from pathlib import Path

from app.report_html_rewrite import (
    file_url_to_path,
    rewrite_file_attributes,
    rewrite_report_html,
)


def test_rewrite_href_file_uri_to_reports_file(tmp_path: Path) -> None:
    (tmp_path / "playlists").mkdir()
    media = tmp_path / "playlists" / "clip.webm"
    media.write_bytes(b"x")
    uri = media.resolve().as_uri()
    html = f'<html><body><a href="{uri}">watch</a></body></html>'
    out = rewrite_file_attributes(
        html,
        tmp_path,
        ["logs", "playlists", "channels", "videos"],
    )
    assert "file:" not in out.lower()
    assert "/reports/file?rel=playlists%2Fclip.webm" in out


def test_rewrite_skips_outside_allowlist(tmp_path: Path) -> None:
    (tmp_path / "playlists").mkdir()
    other = (tmp_path.parent / "secret" / "a.mp4").resolve()
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_bytes(b"x")
    uri = other.as_uri()
    html = f'<a href="{uri}">x</a>'
    out = rewrite_file_attributes(
        html,
        tmp_path,
        ["playlists"],
    )
    assert uri in out


def test_rewrite_report_injects_shim(tmp_path: Path) -> None:
    html = "<html><head></head><body></body></html>"
    out = rewrite_report_html(
        html,
        tmp_path,
        ["logs"],
    )
    assert "archive-console-viewer-shim" in out
    assert "/reports/file?rel=" in out


def test_file_url_to_path_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "z.txt"
    f.write_text("a", encoding="utf-8")
    u = f.resolve().as_uri()
    p = file_url_to_path(u)
    assert p is not None
    assert p.resolve() == f.resolve()
