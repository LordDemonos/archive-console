"""Unit tests for bookmark URL normalization and same-host label rules."""

from __future__ import annotations

import pytest

from app.bookmark_utils import (
    assert_safe_http_url_for_ssrf,
    bookmark_labels_for_urls,
    normalize_bookmark_url,
)


def test_normalize_strips_fragment() -> None:
    assert normalize_bookmark_url("https://Example.com/foo#bar") == "https://example.com/foo"


def test_normalize_requires_http_https() -> None:
    with pytest.raises(ValueError, match="only http"):
        normalize_bookmark_url("ftp://a.com/")
    with pytest.raises(ValueError, match="only http"):
        normalize_bookmark_url("javascript:alert(1)")


def test_normalize_empty() -> None:
    with pytest.raises(ValueError):
        normalize_bookmark_url("")


def test_ssrf_blocks_localhost_hostname() -> None:
    with pytest.raises(ValueError):
        assert_safe_http_url_for_ssrf("http://localhost/foo")


def test_ssrf_blocks_literal_loopback() -> None:
    with pytest.raises(ValueError):
        assert_safe_http_url_for_ssrf("http://127.0.0.1/")


def test_ssrf_disallows_port_8080() -> None:
    with pytest.raises(ValueError, match="port"):
        assert_safe_http_url_for_ssrf("http://example.com:8080/")


def test_bookmark_labels_first_host_only() -> None:
    urls = ["https://docs.example.com/a", "https://docs.example.com/b"]
    labels, titles = bookmark_labels_for_urls(urls)
    assert labels[0] == "docs.example.com"
    assert "…" in labels[1]
    assert titles == urls


def test_bookmark_labels_collision_path() -> None:
    urls = [
        "https://example.com/",
        "https://example.com/docs",
    ]
    labels, _ = bookmark_labels_for_urls(urls)
    assert labels[0] == "example.com"
    assert labels[1].startswith("example.com")
    assert "docs" in labels[1]


def test_bookmark_labels_invalid_entry() -> None:
    labels, titles = bookmark_labels_for_urls(["not-a-url"])
    assert labels[0] == "Invalid URL"
    assert titles[0] == "not-a-url"
