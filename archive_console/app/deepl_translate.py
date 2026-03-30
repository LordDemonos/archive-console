"""DeepL HTTP API client (server-side only). Never log raw auth keys."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEEPL_FREE_BASE = "https://api-free.deepl.com"
DEEPL_PRO_BASE = "https://api.deepl.com"

# Keys ending with :fx are Free API keys per DeepL documentation.
_FREE_KEY_SUFFIX = ":fx"


class DeepLClientError(Exception):
    """Operator-safe error; message must not contain secrets."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def resolve_deepl_base_url(api_key: str, endpoint_mode: str) -> str:
    m = (endpoint_mode or "auto").strip().lower()
    if m == "free":
        return DEEPL_FREE_BASE
    if m == "pro":
        return DEEPL_PRO_BASE
    k = (api_key or "").strip()
    if k.endswith(_FREE_KEY_SUFFIX):
        return DEEPL_FREE_BASE
    return DEEPL_PRO_BASE


def redact_secrets(text: str, api_key: str | None = None) -> str:
    """Strip likely secrets from error strings for logs and HTTP details."""
    if not text:
        return text
    out = text
    if api_key:
        k = api_key.strip()
        if k and k in out:
            out = out.replace(k, "[redacted]")
        if ":fx" in k:
            base = k[: -len(_FREE_KEY_SUFFIX)]
            if base and base in out:
                out = out.replace(base, "[redacted]")
    out = re.sub(
        r"DeepL-Auth-Key\s+[\w\-:.]+",
        "DeepL-Auth-Key [redacted]",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"(Authorization|auth_key)\s*[:=]\s*\S+",
        r"\1 [redacted]",
        out,
        flags=re.I,
    )
    return out


def effective_deepl_api_key(stored_key: str) -> str:
    env = __import__("os").environ.get("ARCHIVE_CONSOLE_DEEPL_API_KEY", "").strip()
    if env:
        return env
    return (stored_key or "").strip()


def translate_texts(
    texts: list[str],
    *,
    api_key: str,
    source_lang: str,
    target_lang: str,
    endpoint_base: str,
    timeout_sec: float = 60.0,
) -> tuple[list[str], dict[str, Any]]:
    """
    POST /v2/translate with multiple text fields.
    Returns (translated_strings_same_order, usage_meta).
    usage_meta may include character_count if the API returns it.
    """
    if not texts:
        return [], {}
    key = (api_key or "").strip()
    if not key:
        raise DeepLClientError("deepl_key_missing", "DeepL API key is not configured.")
    base = endpoint_base.rstrip("/")
    url = f"{base}/v2/translate"
    tgt = (target_lang or "EN-US").strip()
    data: list[tuple[str, str]] = [("target_lang", tgt)]
    src = (source_lang or "").strip()
    if src and src.lower() != "auto":
        data.append(("source_lang", src))
    for t in texts:
        data.append(("text", t))
    headers = {"Authorization": f"DeepL-Auth-Key {key}"}
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(url, data=data, headers=headers)
    except httpx.RequestError as e:
        msg = redact_secrets(str(e), key)
        logger.warning("DeepL request error: %s", msg)
        raise DeepLClientError(
            "deepl_network",
            "Could not reach DeepL (network error). Check your connection.",
        ) from None
    if r.status_code == 429:
        logger.warning("DeepL rate limit (429)")
        raise DeepLClientError(
            "deepl_rate_limit",
            "DeepL rate limit (HTTP 429). Wait and retry, or check your plan on the DeepL dashboard.",
        )
    if r.status_code >= 500:
        body = redact_secrets(r.text[:500], key)
        logger.warning("DeepL server error %s: %s", r.status_code, body)
        raise DeepLClientError(
            "deepl_server",
            f"DeepL server error (HTTP {r.status_code}). Try again later.",
        )
    if r.status_code != 200:
        body = redact_secrets(r.text[:500], key)
        logger.warning("DeepL error %s: %s", r.status_code, body)
        raise DeepLClientError(
            "deepl_client_error",
            f"DeepL request failed (HTTP {r.status_code}). Check API key and target language.",
        )
    try:
        payload = r.json()
    except Exception:
        raise DeepLClientError(
            "deepl_bad_response",
            "DeepL returned a non-JSON response.",
        ) from None
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise DeepLClientError(
            "deepl_bad_response",
            "DeepL response missing translations array.",
        )
    out: list[str] = []
    for item in translations:
        if isinstance(item, dict) and "text" in item:
            out.append(str(item["text"]))
        else:
            raise DeepLClientError(
                "deepl_bad_response",
                "Unexpected DeepL translation entry shape.",
            )
    if len(out) != len(texts):
        raise DeepLClientError(
            "deepl_bad_response",
            "DeepL returned a different number of translations than requested.",
        )
    usage: dict[str, Any] = {}
    # Optional billing / usage fields (plan-dependent).
    for k in ("character_count", "characters", "billed_characters"):
        if k in payload:
            usage[k] = payload[k]
    return out, usage
