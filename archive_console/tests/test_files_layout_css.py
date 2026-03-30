"""Sanity: Files workspace uses fixed shell height (not content-sized from list)."""

from pathlib import Path


def test_files_workspace_shell_and_storage_key():
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(
        encoding="utf-8"
    )
    js = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert ".files-workspace" in css
    assert ".files-workspace-shell" in css
    assert "--files-workspace-height" in css
    block_start = css.find(".files-workspace {")
    assert block_start >= 0
    block_end = css.find("\n}", block_start)
    block = css[block_start:block_end]
    assert "min-height: 0" in block
    assert "calc(100vh" not in block
    assert 'files.workspace.height' in js


def test_files_index_includes_workspace_shell():
    html = (Path(__file__).resolve().parent.parent / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="filesWorkspaceShell"' in html
    assert 'id="filesWorkspaceResizeY"' in html


def test_index_favicon_manifest_and_static_assets():
    base = Path(__file__).resolve().parent.parent
    html = (base / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon"' in html
    assert "/static/favicon-32.png" in html
    assert "/static/app-icon-128.png" in html
    assert 'rel="manifest"' in html
    assert "/static/manifest.json" in html
    assert 'class="brand-mark-img"' in html
    assert (base / "static" / "app-icon.svg").is_file()
    manifest = (base / "static" / "manifest.json").read_text(encoding="utf-8")
    assert "Archive Console" in manifest
    assert "/static/icon-512.png" in manifest


def test_files_view_active_is_flex_column():
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(
        encoding="utf-8"
    )
    assert "#view-library.is-active" in css
    assert "min-height: 0" in css
