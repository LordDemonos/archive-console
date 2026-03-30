"""POST /api/shutdown — loopback guard and confirmation body."""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client_shutdown_ok(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ARCHIVE_CONSOLE_PYTEST_SHUTDOWN", "1")
    return TestClient(app)


def test_shutdown_rejects_wrong_confirm(client_shutdown_ok: TestClient) -> None:
    r = client_shutdown_ok.post("/api/shutdown", json={"confirm": "no"})
    assert r.status_code == 422


def test_shutdown_rejects_without_pytest_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHIVE_CONSOLE_PYTEST_SHUTDOWN", raising=False)
    with TestClient(app) as client:
        r = client.post("/api/shutdown", json={"confirm": "SHUTDOWN"})
    assert r.status_code == 403


def test_shutdown_requires_token_when_set(
    client_shutdown_ok: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARCHIVE_SHUTDOWN_TOKEN", "secret123")
    r = client_shutdown_ok.post("/api/shutdown", json={"confirm": "SHUTDOWN"})
    assert r.status_code == 403
    r2 = client_shutdown_ok.post(
        "/api/shutdown",
        json={"confirm": "SHUTDOWN"},
        headers={"X-Archive-Shutdown-Token": "wrong"},
    )
    assert r2.status_code == 403
    with mock.patch("app.shutdown.request_shutdown") as q:
        r3 = client_shutdown_ok.post(
            "/api/shutdown",
            json={"confirm": "SHUTDOWN"},
            headers={"X-Archive-Shutdown-Token": "secret123"},
        )
    assert r3.status_code == 200
    assert r3.json() == {"ok": True}
    q.assert_called_once()


def test_shutdown_no_get(client_shutdown_ok: TestClient) -> None:
    r = client_shutdown_ok.get("/api/shutdown")
    assert r.status_code == 405
