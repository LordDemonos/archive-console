"""Folder batch rename: enumerate, skip done, done log."""

from __future__ import annotations

from pathlib import Path

from app.rename_folder import (
    collect_rename_rels_under_dir,
    done_new_rels_for_batch,
    folder_candidates_payload,
    partition_pending_rels,
    pipeline_fingerprint,
)
from app.rename_pipeline import RenamePreviewOptions
from app.settings import ConsoleState, append_rename_done_log


def test_collect_rename_rels_skips_sidecars(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    folder = root / "playlists" / "WL"
    folder.mkdir(parents=True)
    (folder / "a.mp4").write_bytes(b"x")
    (folder / "a.info.json").write_text("{}")
    (folder / "a.description").write_text("d")
    rels = collect_rename_rels_under_dir(
        root.resolve(),
        "playlists/WL",
        ["playlists"],
        recursive=False,
    )
    assert rels == ["playlists/WL/a.mp4"]


def test_done_log_skips_on_rescan(tmp_path: Path) -> None:
    root = tmp_path / "ar"
    folder = root / "playlists" / "arch"
    folder.mkdir(parents=True)
    old = folder / "old.mp4"
    old.write_bytes(b"x")
    opt = RenamePreviewOptions(use_deepl=True, use_exif=False)
    fp = pipeline_fingerprint(opt, target_lang="EN-US", source_lang="", endpoint_mode="auto")
    st = ConsoleState(archive_root=str(root.resolve()))
    st = append_rename_done_log(
        st,
        folder_rel="playlists/arch",
        pipeline_fp=fp,
        run_id="run1",
        items=[
            {
                "rel": "playlists/arch/old.mp4",
                "new_rel": "playlists/arch/new.mp4",
                "status": "ok",
            }
        ],
    )
    payload = folder_candidates_payload(
        archive_root=root.resolve(),
        allowed_prefixes=["playlists"],
        folder_rel="playlists/arch",
        done_log=st.rename_done_log,
        opt=opt,
        target_lang="EN-US",
        source_lang="",
        endpoint_mode="auto",
        skip_done=True,
    )
    assert payload["total_in_folder"] == 1
    assert payload["pending_count"] == 1

    new = folder / "new.mp4"
    new.write_bytes(b"x")
    old.unlink()
    payload2 = folder_candidates_payload(
        archive_root=root.resolve(),
        allowed_prefixes=["playlists"],
        folder_rel="playlists/arch",
        done_log=st.rename_done_log,
        opt=opt,
        target_lang="EN-US",
        source_lang="",
        endpoint_mode="auto",
        skip_done=True,
    )
    assert payload2["pending_count"] == 0
    assert payload2["skipped_done"] == 1


def test_partition_pending_rels() -> None:
    done = {"a/b.mp4"}
    pending, skipped = partition_pending_rels(["a/a.mp4", "a/b.mp4", "a/c.mp4"], done)
    assert pending == ["a/a.mp4", "a/c.mp4"]
    assert skipped == 1


def test_done_new_rels_for_batch_filters_pipeline() -> None:
    log = [
        {
            "folder_rel": "playlists/x",
            "pipeline_fp": "aaa",
            "old_rel": "playlists/x/1.mp4",
            "new_rel": "playlists/x/one.mp4",
            "status": "ok",
        },
        {
            "folder_rel": "playlists/x",
            "pipeline_fp": "bbb",
            "old_rel": "playlists/x/2.mp4",
            "new_rel": "playlists/x/two.mp4",
            "status": "ok",
        },
    ]
    done = done_new_rels_for_batch(log, folder_rel="playlists/x", pipeline_fp="aaa")
    assert done == {"playlists/x/one.mp4"}
