"""Rename preview HTTP: error mapping and DeepL mocks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.main as main
import app.settings as sm


def _patch_deepl_preview(monkeypatch_or_patches, fake_translate):
    """Patch usage lookup and batched translate for rename preview tests."""

    def fake_usage(**kwargs):  # noqa: ANN003, ANN201
        return {"character_count": 0, "character_limit": 500000}

    if hasattr(monkeypatch_or_patches, "setattr"):
        monkeypatch_or_patches.setattr(
            "app.rename_pipeline.fetch_usage", fake_usage
        )
        monkeypatch_or_patches.setattr(
            "app.rename_pipeline.translate_texts_batched", fake_translate
        )
        return

    class _DualPatch:
        def __enter__(self):
            self._usage = patch("app.rename_pipeline.fetch_usage", fake_usage)
            self._translate = patch(
                "app.rename_pipeline.translate_texts_batched", fake_translate
            )
            self._usage.__enter__()
            self._translate.__enter__()
            return self

        def __exit__(self, *args):
            self._translate.__exit__(*args)
            self._usage.__exit__(*args)

    return _DualPatch()


@pytest.fixture
def rename_preview_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "playlists").mkdir()
    (ar / "playlists" / "20230101_hello.mp4").write_bytes(b"x")
    (ar / "playlists" / "20230101_world.mp4").write_bytes(b"x")
    (ar / "playlists" / "Hello-dQw4w9WgXcQ.mp4").write_bytes(b"x")
    st_path = tmp_path / "state.json"
    st_path.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": 8756,
                "archive_root": str(ar),
                "allowlisted_rel_prefixes": ["playlists"],
                "deepl_api_key": "secret:fx",
                "deepl_endpoint_mode": "auto",
                "deepl_source_lang": "",
                "deepl_target_lang": "EN-US",
                "features": {
                    "scheduler_enabled": False,
                    "notifications_stub": False,
                    "require_cookie_confirm_manual": False,
                    "tray_notify_before_schedule": False,
                },
                "schedules": [],
                "run_history": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sm, "DEFAULT_STATE_PATH", st_path)
    main._state = None
    main._manager = None
    with TestClient(app) as client:
        yield client


def test_rename_preview_ok_mock_deepl(rename_preview_env: TestClient) -> None:
    def fake_translate(texts, **kwargs):  # noqa: ANN003, ANN201
        return [t.upper() for t in texts], {"character_count": 3}

    with _patch_deepl_preview(None, fake_translate):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/20230101_hello.mp4"],
                "max_files": 50,
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                    "whole_basename": False,
                    "preserve_youtube_id": True,
                    "preserve_brackets": True,
                    "pipeline_order": "exif_then_deepl",
                    "exif_template": "",
                    "exif_missing_policy": "keep_basename",
                },
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"][0]["proposed_basename"] == "20230101_HELLO.mp4"


def test_rename_preview_youtube_id_preserved_when_option_on(
    rename_preview_env: TestClient,
) -> None:
    """Trailing -id is split off for DeepL and reattached after translation."""

    def fake_translate(texts, **kwargs):  # noqa: ANN003, ANN201
        return [t.upper() for t in texts], {}

    with _patch_deepl_preview(None, fake_translate):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/Hello-dQw4w9WgXcQ.mp4"],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                    "whole_basename": False,
                    "preserve_youtube_id": True,
                    "preserve_brackets": True,
                },
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["proposed_basename"] == "HELLO-dQw4w9WgXcQ.mp4"


def test_rename_preview_youtube_id_stripped_when_option_off(
    rename_preview_env: TestClient,
) -> None:
    """Unchecked: -id is removed from stem (not sent to DeepL, not in proposed name)."""

    def fake_translate(texts, **kwargs):  # noqa: ANN003, ANN201
        return [t.upper() for t in texts], {}

    with _patch_deepl_preview(None, fake_translate):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/Hello-dQw4w9WgXcQ.mp4"],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                    "whole_basename": False,
                    "preserve_youtube_id": False,
                    "preserve_brackets": True,
                },
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["proposed_basename"] == "HELLO.mp4"


def test_rename_preview_maps_unexpected_to_502(rename_preview_env: TestClient) -> None:
    with patch(
        "app.main.build_rename_preview",
        side_effect=RuntimeError("boom"),
    ):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/20230101_hello.mp4"],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                },
            },
        )
    assert r.status_code == 502
    body = r.json()
    det = body.get("detail")
    assert isinstance(det, dict)
    assert det.get("error_code") == "rename_preview_unexpected"
    assert "RuntimeError" in str(det.get("message") or "")


def test_rename_preview_deepl_batch_len_mismatch_is_400(rename_preview_env: TestClient) -> None:
    """Broken translate mock must not surface as 502 TypeError to the client."""

    def bad_translate(_texts, **kwargs):  # noqa: ANN001, ANN201
        return ["only_one"], {}

    with _patch_deepl_preview(None, bad_translate):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": [
                    "playlists/20230101_hello.mp4",
                    "playlists/20230101_world.mp4",
                ],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                },
            },
        )
    assert r.status_code == 400
    body = r.json()
    det = body.get("detail")
    assert isinstance(det, dict)
    assert det.get("error_code") == "rename_preview_validation"
    assert "mismatch" in str(det.get("message") or "").lower()


def test_rename_preview_deepl_non_list_translation_structured_502(
    rename_preview_env: TestClient,
) -> None:
    """Regression: translate_texts used to allow len(None) → TypeError → opaque 500."""

    def bad_translate(_texts, **kwargs):  # noqa: ANN001, ANN201
        return None, {}

    with _patch_deepl_preview(None, bad_translate):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/20230101_hello.mp4"],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                },
            },
        )
    assert r.status_code == 502
    det = r.json().get("detail")
    assert isinstance(det, dict)
    assert det.get("error_code") == "deepl_bad_response"
    assert "message" in det


def test_rename_preview_type_error_structured(rename_preview_env: TestClient) -> None:
    with patch(
        "app.main.build_rename_preview",
        side_effect=TypeError("surrogate"),
    ):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/20230101_hello.mp4"],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                },
            },
        )
    assert r.status_code == 502
    det = r.json().get("detail")
    assert isinstance(det, dict)
    assert det.get("error_code") == "rename_preview_type_error"


def test_archive_console_doc_route(rename_preview_env: TestClient) -> None:
    r = rename_preview_env.get("/docs/archive-console")
    assert r.status_code == 200
    assert b"Rename" in r.content or b"rename" in r.content


def _ledger_first_row() -> dict:
    data = json.loads(sm.DEFAULT_STATE_PATH.read_text(encoding="utf-8"))
    runs = data.get("rename_runs") or []
    assert runs, "expected at least one rename_runs row"
    return runs[0]


def test_rename_preview_unexpected_persists_sanitized_ledger(
    rename_preview_env: TestClient,
) -> None:
    with patch(
        "app.main.build_rename_preview",
        side_effect=RuntimeError("boom"),
    ):
        r = rename_preview_env.post(
            "/api/rename/preview",
            json={
                "rels": ["playlists/20230101_hello.mp4"],
                "options": {
                    "use_deepl": True,
                    "use_exif": False,
                },
            },
        )
    assert r.status_code == 502
    row = _ledger_first_row()
    assert row.get("status") == "fail"
    assert row.get("ledger_kind") == "rename_preview_failed"
    assert row.get("error_code") == "rename_preview_unexpected"
    assert row.get("rel_count") == 1
    assert row.get("items") == []
    assert row.get("diagnostic_ref")
    assert len(row["diagnostic_ref"]) >= 8
    assert "boom" not in json.dumps(row)
    assert "traceback" not in json.dumps(row).lower()


def test_rename_preview_validation_persists_ledger(rename_preview_env: TestClient) -> None:
    r = rename_preview_env.post(
        "/api/rename/preview",
        json={
            "rels": ["playlists/20230101_hello.mp4"],
            "options": {
                "use_deepl": False,
                "use_exif": True,
                "exif_template": "",
            },
        },
    )
    assert r.status_code == 400
    row = _ledger_first_row()
    assert row.get("status") == "fail"
    assert row.get("ledger_kind") == "rename_preview_failed"
    assert row.get("error_code") == "rename_preview_validation"


def test_rename_apply_unknown_preview_persists_ledger(
    rename_preview_env: TestClient,
) -> None:
    r = rename_preview_env.post(
        "/api/rename/apply",
        json={"preview_id": "deadbeefcafe"},
    )
    assert r.status_code == 400
    row = _ledger_first_row()
    assert row.get("ledger_kind") == "rename_apply_failed"
    assert row.get("error_code") == "rename_apply_validation"
    assert row.get("preview_id")


def test_build_rename_preview_max_files_string_coerced_no_typeerror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Direct callers may pass max_files as str; min(str, int) raised TypeError."""
    from app.rename_pipeline import RenamePreviewOptions, build_rename_preview

    ar = tmp_path / "archive"
    ar.mkdir()
    (ar / "playlists").mkdir()
    (ar / "playlists" / "a.mp4").write_bytes(b"x")

    def fake_translate(texts, **kwargs):  # noqa: ANN003, ANN201
        return list(texts), {}

    _patch_deepl_preview(monkeypatch, fake_translate)
    opt = RenamePreviewOptions(
        use_deepl=True,
        use_exif=False,
    )
    out = build_rename_preview(
        archive_root=ar,
        allowed_prefixes=["playlists"],
        rels=["playlists/a.mp4"],
        opt=opt,
        stored_api_key="k:fx",
        endpoint_mode="auto",
        source_lang="",
        target_lang="EN-US",
        max_files="30",  # type: ignore[arg-type]
        exiftool_exe="",
        exiftool_timeout_sec=45.0,
    )
    assert out.get("preview_id")
    assert len(out.get("rows") or []) == 1
