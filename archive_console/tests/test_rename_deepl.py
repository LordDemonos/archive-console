"""DeepL client behavior (mocked HTTP)."""

from __future__ import annotations

import os

import pytest

from app.deepl_translate import (
    DeepLClientError,
    resolve_deepl_base_url,
    translate_texts,
)


def test_resolve_auto_free_suffix() -> None:
    assert (
        resolve_deepl_base_url("abc:fx", "auto")
        == "https://api-free.deepl.com"
    )


def test_resolve_auto_pro() -> None:
    assert resolve_deepl_base_url("abc", "auto") == "https://api.deepl.com"


def test_translate_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {
                "translations": [
                    {"text": "Hello"},
                    {"text": "World"},
                ],
                "character_count": 10,
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, data=None, headers=None):
            assert "translate" in url
            texts = [v for k, v in data if k == "text"]
            assert texts == ["a", "b"]
            assert headers.get("Authorization", "").startswith("DeepL-Auth-Key ")
            return FakeResp()

    monkeypatch.setattr("app.deepl_translate.httpx.Client", FakeClient)
    out, usage = translate_texts(
        ["a", "b"],
        api_key="k:fx",
        source_lang="",
        target_lang="EN-US",
        endpoint_base="https://api-free.deepl.com",
    )
    assert out == ["Hello", "World"]
    assert usage.get("character_count") == 10


def test_translate_429(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 429

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, data=None, headers=None):
            return FakeResp()

    monkeypatch.setattr("app.deepl_translate.httpx.Client", FakeClient)
    with pytest.raises(DeepLClientError) as ei:
        translate_texts(
            ["x"],
            api_key="key:fx",
            source_lang="",
            target_lang="EN-US",
            endpoint_base="https://api-free.deepl.com",
        )
    assert ei.value.code == "deepl_rate_limit"


@pytest.mark.skipif(
    not os.environ.get("DEEPL_TEST_KEY"),
    reason="Set DEEPL_TEST_KEY for optional live DeepL call",
)
def test_deepl_live_smoke() -> None:
    key = os.environ["DEEPL_TEST_KEY"].strip()
    out, _u = translate_texts(
        ["Hallo"],
        api_key=key,
        source_lang="DE",
        target_lang="EN-US",
        endpoint_base=resolve_deepl_base_url(key, "auto"),
    )
    assert len(out) == 1
    assert out[0]
