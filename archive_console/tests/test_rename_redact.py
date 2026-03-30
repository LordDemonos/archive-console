"""Redaction helpers must not leak DeepL keys into logs."""

from __future__ import annotations

from app.deepl_translate import redact_secrets


def test_redact_full_key() -> None:
    k = "279a2e9d-83b3-c416-7e2d-f721593e42a0:fx"
    msg = f"error calling DeepL with {k} failed"
    out = redact_secrets(msg, k)
    assert ":fx" not in out or "[redacted]" in out
    assert k not in out


def test_redact_auth_header_snippet() -> None:
    msg = 'header DeepL-Auth-Key 279a2e9d:fx and tail'
    out = redact_secrets(msg, None)
    assert "DeepL-Auth-Key [redacted]" in out
