"""Sanity: Library files workspace uses document flow (min-heights), not JS-fixed band heights."""

from pathlib import Path


def test_files_workspace_shell_document_flow_css():
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(
        encoding="utf-8"
    )
    js = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert ".files-workspace" in css
    assert ".files-workspace-shell" in css
    assert "min-height: 300px" in css
    assert "#view-library .files-workspace-shell" in css
    block_start = css.find(".files-workspace {")
    assert block_start >= 0
    block_end = css.find("\n}", block_start)
    block = css[block_start:block_end]
    assert "overflow: visible" in block
    assert "calc(100vh" not in block
    assert "library.workspace.height" not in js
    assert "archive_console_library_player_band_px" not in js
    assert "archive_console_library_file_list_font_px" in js


def test_library_r1_files_list_scroll_chain_css():
    """R1 #filesSplit flex item + Files grid cell must not forward #fileList max-content height."""
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(
        encoding="utf-8"
    )
    assert "#view-library .files-workspace-shell .files-workspace-split-wrap" in css
    assert "#view-library .files-library-r1-split > .library-panel--list" in css
    block = css[css.find("#view-library .files-workspace-shell .files-workspace-split-wrap") :]
    block = block[: block.find("\n\n", 1)]
    assert "min-height: 0" in block
    assert "overflow: hidden" in block
    list_block_start = css.find("#view-library .files-library-r1-split > .library-panel--list")
    assert list_block_start >= 0
    list_block = css[list_block_start : list_block_start + 400]
    assert "overflow: hidden" in list_block


def test_files_index_includes_workspace_shell_and_selection_help():
    html = (Path(__file__).resolve().parent.parent / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="view-getting-started"' in html
    assert 'data-view="getting-started"' in html
    assert "archive_console.getting_started" in Path(
        __file__
    ).resolve().parent.parent.joinpath("static", "app.js").read_text(encoding="utf-8")
    assert 'id="filesWorkspaceShell"' in html
    assert 'id="librarySelectionHelp"' in html
    assert 'id="libraryPlayerKeysHint"' in html
    assert 'id="filesWorkspaceResizeY"' not in html
    assert 'id="filesLibraryR2R3Stack"' not in html
    assert 'id="filesLibraryResizeYR2R3"' not in html
    assert "files-library-player-band" in html
    assert "files-library-export-band" in html
    assert "btnLibraryFileListFontMinus" in html
    assert "files-library-r1-split" in html
    assert "library-panel" in html
    assert 'id="btnFileDetailSendRename"' in html
    assert 'id="btnFileDetailAddPlayerQueue"' in html
    assert 'id="libraryViewToast"' in html
    assert "library-panel__title--files" in html


def test_library_layout_no_vertical_resize_storage_keys_in_js():
    js = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "initFilesWorkspaceShellResize" not in js
    assert "initLibraryPlayerBandResize" not in js
    assert "LIBRARY_PLAYER_BAND_MIN_PX" not in js


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


def test_library_panels_and_player_queue_overflow_documented():
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(
        encoding="utf-8"
    )
    assert "#view-library .library-panel--meta .library-panel__body" in css
    assert "overflow-y: visible" in css
    assert ".files-player-queue-scroll" in css
    assert "#view-library .files-library-player-band .files-player-queue-scroll" in css
    assert ".files-library-player-band .files-player-video-frame" in css
    assert "min-height: 420px" in css


def test_nav_item_hidden_beats_display_flex():
    """Regression: Settings → hide Getting started uses [hidden]; .nav-item must not override it."""
    css = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(
        encoding="utf-8"
    )
    assert ".nav-item[hidden]" in css
    assert "display: none !important" in css
