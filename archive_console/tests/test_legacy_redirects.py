"""Legacy /logs and /reports paths redirect to unified History & reports view."""

from fastapi.responses import RedirectResponse

from app.main import legacy_logs_redirect, legacy_reports_redirect


def test_legacy_logs_redirect_response() -> None:
    r = legacy_logs_redirect()
    assert isinstance(r, RedirectResponse)
    assert r.status_code == 302
    assert r.headers["location"] == "/?view=history&section=outcomes"


def test_legacy_reports_redirect_response() -> None:
    r = legacy_reports_redirect()
    assert isinstance(r, RedirectResponse)
    assert r.status_code == 302
    assert r.headers["location"] == "/?view=history&section=reports"
