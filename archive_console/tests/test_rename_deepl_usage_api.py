"""Rename DeepL usage API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def usage_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    root = tmp_path / "ar"
    root.mkdir()
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("ARCHIVE_CONSOLE_STATE_PATH", str(state_path))
    from app import main as main_mod

    main_mod._state = None
    st = main_mod.load_state()
    st.archive_root = str(root)
    st.deepl_api_key = "secret:fx"
    main_mod.save_state(st, state_path)
    main_mod._state = st
    return TestClient(main_mod.app)


def test_deepl_usage_not_configured(
    usage_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_mod

    st = main_mod.load_state()
    st.deepl_api_key = ""
    main_mod.save_state(st)
    main_mod._state = st
    r = usage_client.get("/api/rename/deepl-usage")
    assert r.status_code == 200
    j = r.json()
    assert j["configured"] is False


def test_deepl_usage_ok(usage_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main as main_mod

    def fake_usage(**kwargs):
        return {"character_count": 12000, "character_limit": 500000}

    monkeypatch.setattr(main_mod, "fetch_usage", fake_usage)
    r = usage_client.get("/api/rename/deepl-usage?queue_size=120")
    assert r.status_code == 200
    j = r.json()
    assert j["configured"] is True
    assert j["character_count"] == 12000
    assert j["character_limit"] == 500000
    assert j["character_remaining"] == 488000
    assert j["estimated_api_batches"] == 3
