"""DeepL HTTP API client (server-side only). Never log raw auth keys."""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

DEEPL_FREE_BASE = "https://api-free.deepl.com"
DEEPL_PRO_BASE = "https://api.deepl.com"

# Keys ending with :fx are Free API keys per DeepL documentation.
_FREE_KEY_SUFFIX = ":fx"

# DeepL documented / practical per-request limits (see developers.deepl.com/docs/resources/usage-limits).
DEEPL_MAX_TEXTS_PER_REQUEST = 50
DEEPL_MAX_REQUEST_BODY_BYTES = 76 * 1024
DEEPL_BATCH_DELAY_SEC = 0.05
DEEPL_429_MAX_RETRIES = 3
DEEPL_429_BACKOFF_BASE_SEC = 2.0


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
    """
    Prefer env override; normalize pasted keys (strip + drop stray CR/LF).
    """
    env = __import__("os").environ.get("ARCHIVE_CONSOLE_DEEPL_API_KEY", "").strip()
    raw = env if env else (stored_key or "").strip()
    raw = raw.replace("\r", "").replace("\n", "").strip()
    return raw


def _single_request_body_size(
    texts: list[str],
    target_lang: str,
    source_lang: str,
) -> int:
    fields: list[tuple[str, str]] = [("target_lang", (target_lang or "EN-US").strip())]
    src = (source_lang or "").strip()
    if src and src.lower() != "auto":
        fields.append(("source_lang", src))
    for t in texts:
        fields.append(("text", "" if t is None else str(t)))
    return len(urlencode(fields).encode("utf-8"))


def chunk_texts_for_deepl(
    texts: list[str],
    *,
    target_lang: str,
    source_lang: str,
    max_texts: int = DEEPL_MAX_TEXTS_PER_REQUEST,
    max_body_bytes: int = DEEPL_MAX_REQUEST_BODY_BYTES,
) -> list[list[str]]:
    """Split texts into API-sized chunks (max 50 texts and ~76 KiB body per request)."""
    if not texts:
        return []
    chunks: list[list[str]] = []
    current: list[str] = []
    for text in texts:
        candidate = current + [text]
        too_many = len(candidate) > max_texts
        too_large = _single_request_body_size(
            candidate, target_lang, source_lang
        ) > max_body_bytes
        if too_many or too_large:
            if current:
                chunks.append(current)
                current = [text]
            else:
                chunks.append([text])
                current = []
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def fetch_usage(
    *,
    api_key: str,
    endpoint_base: str,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    """GET /v2/usage — characters used and limit for the current billing period."""
    key = (api_key or "").strip()
    if not key:
        raise DeepLClientError("deepl_key_missing", "DeepL API key is not configured.")
    base = endpoint_base.rstrip("/")
    url = f"{base}/v2/usage"
    req_headers = {"Authorization": f"DeepL-Auth-Key {key}"}
    try:
        timeout_total = float(timeout_sec)
    except (TypeError, ValueError):
        timeout_total = 30.0
    if not (timeout_total == timeout_total) or timeout_total <= 0:
        timeout_total = 30.0
    try:
        with httpx.Client(timeout=timeout_total) as client:
            r = client.get(url, headers=req_headers)
    except httpx.RequestError as e:
        msg = redact_secrets(str(e), key)
        logger.warning("DeepL usage request error: %s", msg)
        raise DeepLClientError(
            "deepl_network",
            "Could not reach DeepL (network error). Check your connection.",
        ) from None
    if r.status_code == 429:
        raise DeepLClientError(
            "deepl_rate_limit",
            "DeepL rate limit (HTTP 429). Wait and retry.",
        )
    if r.status_code >= 500:
        raise DeepLClientError(
            "deepl_server",
            f"DeepL server error (HTTP {r.status_code}). Try again later.",
        )
    if r.status_code != 200:
        body = redact_secrets(r.text[:500], key)
        logger.warning("DeepL usage error %s: %s", r.status_code, body)
        raise DeepLClientError(
            "deepl_client_error",
            f"DeepL usage request failed (HTTP {r.status_code}).",
        )
    try:
        payload = r.json()
    except Exception:
        raise DeepLClientError(
            "deepl_bad_response",
            "DeepL returned a non-JSON usage response.",
        ) from None
    if not isinstance(payload, dict):
        raise DeepLClientError(
            "deepl_bad_response",
            "DeepL usage response has unexpected shape.",
        )
    out: dict[str, Any] = {}
    for k in (
        "character_count",
        "character_limit",
        "document_count",
        "document_limit",
    ):
        if k in payload:
            try:
                out[k] = int(payload[k])
            except (TypeError, ValueError):
                out[k] = payload[k]
    return out


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
    try:
        timeout_total = float(timeout_sec)
    except (TypeError, ValueError):
        timeout_total = 60.0
    if not (timeout_total == timeout_total) or timeout_total <= 0:  # NaN or non-positive
        timeout_total = 60.0
    key = (api_key or "").strip()
    if not key:
        raise DeepLClientError("deepl_key_missing", "DeepL API key is not configured.")
    base = endpoint_base.rstrip("/")
    url = f"{base}/v2/translate"
    tgt = (target_lang or "EN-US").strip()
    # DeepL requires repeated "text=" fields. httpx 0.28 + httpcore can raise
    # TypeError (h11: bytes join got tuple) when data= is a list of pairs; build
    # the x-www-form-urlencoded body explicitly instead.
    fields: list[tuple[str, str]] = [("target_lang", tgt)]
    src = (source_lang or "").strip()
    if src and src.lower() != "auto":
        fields.append(("source_lang", src))
    for t in texts:
        text_val = "" if t is None else str(t)
        fields.append(("text", text_val))
    body = urlencode(fields)
    req_headers = {
        "Authorization": f"DeepL-Auth-Key {key}",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
    try:
        with httpx.Client(timeout=timeout_total) as client:
            r = client.post(
                url,
                content=body.encode("utf-8"),
                headers=req_headers,
            )
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
    if r.status_code == 456:
        logger.warning("DeepL quota exceeded (456)")
        raise DeepLClientError(
            "deepl_quota_exceeded",
            "DeepL monthly character quota exceeded (HTTP 456). "
            "Reduce the queue, wait for the billing period to reset, or upgrade your plan.",
        )
    if r.status_code == 413:
        logger.warning("DeepL payload too large (413)")
        raise DeepLClientError(
            "deepl_payload_too_large",
            "DeepL request too large (HTTP 413). Try fewer or shorter filenames per preview batch.",
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


def translate_texts_batched(
    texts: list[str],
    *,
    api_key: str,
    source_lang: str,
    target_lang: str,
    endpoint_base: str,
    timeout_sec: float = 60.0,
    batch_delay_sec: float = DEEPL_BATCH_DELAY_SEC,
) -> tuple[list[str], dict[str, Any]]:
    """
    Translate with per-request chunking (50 texts / ~76 KiB), short pauses, and 429 retry.
    Returns (translated_strings_same_order, merged usage meta).
    """
    if not texts:
        return [], {}
    chunks = chunk_texts_for_deepl(
        texts,
        target_lang=target_lang,
        source_lang=source_lang,
    )
    all_out: list[str] = []
    billed_total = 0
    for i, chunk in enumerate(chunks):
        if i > 0 and batch_delay_sec > 0:
            time.sleep(batch_delay_sec)
        last_err: DeepLClientError | None = None
        for attempt in range(DEEPL_429_MAX_RETRIES + 1):
            try:
                out, usage = translate_texts(
                    chunk,
                    api_key=api_key,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    endpoint_base=endpoint_base,
                    timeout_sec=timeout_sec,
                )
                last_err = None
                break
            except DeepLClientError as e:
                last_err = e
                if e.code == "deepl_rate_limit" and attempt < DEEPL_429_MAX_RETRIES:
                    delay = DEEPL_429_BACKOFF_BASE_SEC * (2**attempt)
                    logger.info(
                        "DeepL 429 on batch %s/%s; retry in %.1fs",
                        i + 1,
                        len(chunks),
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise
        if last_err is not None:
            raise last_err
        all_out.extend(out)
        for k in ("character_count", "characters", "billed_characters"):
            if k in usage:
                try:
                    billed_total += int(usage[k])
                except (TypeError, ValueError):
                    pass
    merged: dict[str, Any] = {"batches": len(chunks)}
    if billed_total:
        merged["character_count"] = billed_total
    return all_out, merged
