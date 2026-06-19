"""DeepL client behavior (mocked HTTP)."""

from __future__ import annotations

import os
from urllib.parse import parse_qsl

import pytest

from app.deepl_translate import (
    DeepLClientError,
    DEEPL_MAX_TEXTS_PER_REQUEST,
    chunk_texts_for_deepl,
    effective_deepl_api_key,
    fetch_usage,
    resolve_deepl_base_url,
    translate_texts,
    translate_texts_batched,
)


def test_effective_deepl_key_strips_newlines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHIVE_CONSOLE_DEEPL_API_KEY", raising=False)
    assert effective_deepl_api_key("abc:fx\n") == "abc:fx"
    assert effective_deepl_api_key("  xy\r\n") == "xy"


def test_resolve_auto_free_suffix() -> None:
    assert (
        resolve_deepl_base_url("abc:fx", "auto")
        == "https://api-free.deepl.com"
    )


def test_resolve_auto_pro() -> None:
    assert resolve_deepl_base_url("abc", "auto") == "https://api.deepl.com"


def test_translate_coerces_none_text_to_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Form fields must be str; None previously risked TypeError in some httpx paths."""

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {
                "translations": [{"text": "x"}, {"text": "y"}],
                "character_count": 2,
            }

    seen: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, content=None, data=None, headers=None):
            assert data is None
            for k, v in parse_qsl(
                content.decode("utf-8"), keep_blank_values=True
            ):
                if k == "text":
                    seen.append((k, v))
            return FakeResp()

    monkeypatch.setattr("app.deepl_translate.httpx.Client", FakeClient)
    out, _u = translate_texts(
        [None, "b"],
        api_key="k:fx",
        source_lang="",
        target_lang="EN-US",
        endpoint_base="https://api-free.deepl.com",
    )
    assert out == ["x", "y"]
    text_fields = [v for k, v in seen if k == "text"]
    assert text_fields == ["", "b"]


def test_translate_timeout_coerced_for_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid timeout types must not raise TypeError inside httpx.Client."""
    timeouts: list[object] = []

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {"translations": [{"text": "z"}], "character_count": 1}

    class FakeClient:
        def __init__(self, *a, **kw):
            timeouts.append(kw.get("timeout"))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, content=None, data=None, headers=None):
            return FakeResp()

    monkeypatch.setattr("app.deepl_translate.httpx.Client", FakeClient)
    translate_texts(
        ["a"],
        api_key="k:fx",
        source_lang="",
        target_lang="EN-US",
        endpoint_base="https://api-free.deepl.com",
        timeout_sec="bogus",  # type: ignore[arg-type]
    )
    assert timeouts[-1] == 60.0
    translate_texts(
        ["a"],
        api_key="k:fx",
        source_lang="",
        target_lang="EN-US",
        endpoint_base="https://api-free.deepl.com",
        timeout_sec="45",  # type: ignore[arg-type]
    )
    assert timeouts[-1] == 45.0


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

        def post(self, url, content=None, data=None, headers=None):
            assert data is None
            assert "translate" in url
            pairs = parse_qsl(content.decode("utf-8"), keep_blank_values=True)
            texts = [v for k, v in pairs if k == "text"]
            assert texts == ["a", "b"]
            assert headers.get("Authorization", "").startswith("DeepL-Auth-Key ")
            assert "application/x-www-form-urlencoded" in headers.get(
                "Content-Type", ""
            )
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

        def post(self, url, content=None, data=None, headers=None):
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


def test_translate_uses_urlencoded_content_not_data_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Regression (diagnostic_ref ed891e68dd24 class): httpx 0.28 + httpcore/h11
    raised TypeError when posting DeepL form as data=[(k,v), ...]:
    'sequence item 1: expected a bytes-like object, tuple found'.
    """
    captured: dict[str, object] = {}

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {"translations": [{"text": "OK"}], "character_count": 1}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, content=None, data=None, headers=None):
            captured["content"] = content
            captured["data"] = data
            return FakeResp()

    monkeypatch.setattr("app.deepl_translate.httpx.Client", FakeClient)
    translate_texts(
        ["single"],
        api_key="k:fx",
        source_lang="",
        target_lang="EN-US",
        endpoint_base="https://api-free.deepl.com",
    )
    assert captured["data"] is None
    assert isinstance(captured["content"], bytes)
    pairs = parse_qsl(
        captured["content"].decode("utf-8"), keep_blank_values=True
    )
    assert [v for k, v in pairs if k == "target_lang"] == ["EN-US"]
    assert [v for k, v in pairs if k == "text"] == ["single"]


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


def test_chunk_texts_respects_max_items() -> None:
    texts = [f"t{i}" for i in range(55)]
    chunks = chunk_texts_for_deepl(
        texts,
        target_lang="EN-US",
        source_lang="",
    )
    assert len(chunks) == 2
    assert len(chunks[0]) == DEEPL_MAX_TEXTS_PER_REQUEST
    assert len(chunks[1]) == 5


def test_fetch_usage_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {"character_count": 1000, "character_limit": 500000}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def get(self, url, headers=None):
            assert url.endswith("/v2/usage")
            return FakeResp()

    monkeypatch.setattr("app.deepl_translate.httpx.Client", FakeClient)
    usage = fetch_usage(
        api_key="k:fx",
        endpoint_base="https://api-free.deepl.com",
    )
    assert usage["character_count"] == 1000
    assert usage["character_limit"] == 500000


def test_translate_texts_batched_splits_and_merges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def fake_once(texts, **kwargs):
        calls.append(len(texts))
        return [f"_{t}_" for t in texts], {"character_count": len(texts)}

    monkeypatch.setattr("app.deepl_translate.translate_texts", fake_once)
    monkeypatch.setattr("app.deepl_translate.time.sleep", lambda _s: None)
    texts = [f"x{i}" for i in range(75)]
    out, usage = translate_texts_batched(
        texts,
        api_key="k:fx",
        source_lang="",
        target_lang="EN-US",
        endpoint_base="https://api-free.deepl.com",
        batch_delay_sec=0,
    )
    assert calls == [50, 25]
    assert len(out) == 75
    assert usage["batches"] == 2
    assert usage["character_count"] == 75


def test_translate_456_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResp:
        status_code = 456

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, content=None, data=None, headers=None):
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
    assert ei.value.code == "deepl_quota_exceeded"
