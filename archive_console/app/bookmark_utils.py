"""
Bookmark URL normalization, same-host label collision rules, SSRF checks, and favicon fetch.

Collision bucket: lowercase hostname only (no eTLD+1 — avoids extra dependencies).
First bookmark per host shows hostname; further ones show ``hostname … <path hint>``.
"""

from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

MAX_BOOKMARK_URLS_PER_LABELS_REQUEST = 200
ICON_MAX_BYTES = 65536
HTML_SNIFF_MAX_BYTES = 65536
FETCH_TIMEOUT_SEC = 6.0
MAX_REDIRECTS = 3
ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "metadata.google.internal",
        "metadata.google",
    }
)

# IPv4 metadata
_METADATA_IPV4 = frozenset({"169.254.169.254"})


class _LinkHrefCollector(HTMLParser):
    """Collect first few <link href> pairs with rel token lists (head only)."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[list[str], str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link" or len(self.links) >= 32:
            return
        ad: dict[str, str] = {}
        for k, v in attrs:
            if k and v is not None:
                ad[k.lower()] = v
        rel_raw = ad.get("rel", "")
        href = ad.get("href", "").strip()
        if not href:
            return
        rel_tokens = [t.lower() for t in rel_raw.split() if t]
        self.links.append((rel_tokens, href))


def _ip_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return True
    if addr.is_multicast or addr.is_reserved:
        return True
    if addr.version == 4:
        return str(addr) in _METADATA_IPV4
    return False


def assert_safe_http_url_for_ssrf(url: str) -> None:
    """
    Raise ValueError if the URL must not be fetched (SSRF / internal).

    Validates hostname resolution to A/AAAA and blocks disallowed addresses.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError("only http and https URLs are allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("missing host")
    host_l = host.lower().rstrip(".")
    if host_l in _BLOCKED_HOSTNAMES:
        raise ValueError("host not allowed")
    if host_l.endswith(".localhost") or host_l.endswith(".local"):
        raise ValueError("host not allowed")
    port = parsed.port
    if port is not None and port not in ALLOWED_PORTS:
        raise ValueError("port not allowed")

    # Literal IP in URL
    try:
        addr = ipaddress.ip_address(host_l)
        if _ip_blocked(addr):
            raise ValueError("address not allowed")
        return
    except ValueError:
        pass  # not a literal IP

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise ValueError(f"host resolution failed: {e}") from e
    if not infos:
        raise ValueError("host resolution empty")
    for _fam, _ty, _pr, _cn, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _ip_blocked(addr):
            raise ValueError("resolved address not allowed")


def normalize_bookmark_url(raw: str) -> str:
    """
    Strip whitespace and fragment; require http(s); return canonical string for storage.

    Raises ValueError on invalid input.
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty URL")
    if len(s) > 2048:
        raise ValueError("URL too long")
    parsed = urlparse(s)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError("only http and https URLs are allowed")
    if not parsed.netloc:
        raise ValueError("missing host")
    # Rebuild without fragment; keep query
    cleaned = urlunparse(
        (
            scheme,
            parsed.netloc.lower() if parsed.netloc else "",
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )
    return cleaned


def hostname_for_bookmark(url: str) -> str:
    """Lowercase hostname without port (for collision grouping)."""
    p = urlparse(url)
    h = (p.hostname or "").lower()
    return h


def _path_differentiator(parsed) -> str:
    path = parsed.path or ""
    if not path or path == "/":
        return "/"
    segments = [x for x in path.split("/") if x]
    if not segments:
        return "/"
    # Use first one or two segments for readability
    parts = segments[:2]
    tail = "/".join(parts)
    if len(tail) > 26:
        tail = tail[:23] + "…"
    return tail


def bookmark_labels_for_urls(urls: list[str]) -> tuple[list[str], list[str]]:
    """
    For each URL (already normalized), compute display label and tooltip (full URL).

    Order-preserving; same host uses collision rules.
    """
    labels: list[str] = []
    titles: list[str] = []
    seen_count: dict[str, int] = {}

    for u in urls:
        titles.append(u)
        try:
            norm = normalize_bookmark_url(u)
        except ValueError:
            labels.append("Invalid URL")
            continue
        p = urlparse(norm)
        host = (p.hostname or "").lower()
        if not host:
            labels.append("Invalid URL")
            continue
        seen_count[host] = seen_count.get(host, 0) + 1
        n = seen_count[host]
        if n == 1:
            labels.append(host)
        else:
            diff = _path_differentiator(p)
            labels.append(f"{host} … {diff}")

    return labels, titles


def _is_probably_image(content_type: str | None, data: bytes) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in (
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    ):
        return True
    if len(data) >= 4 and data[:4] == b"\x89PNG":
        return True
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return True
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if data.startswith(b"<svg") or b"<svg" in data[:200]:
        return True
    return False


def _collect_icon_href_from_html(html: bytes, base_url: str) -> str | None:
    try:
        text = html.decode("utf-8", errors="ignore")
    except Exception:
        return None
    parser = _LinkHrefCollector()
    try:
        parser.feed(text)
    except Exception:
        pass
    best: tuple[int, str] | None = None
    def _rel_pri(rel_tokens: list[str]) -> int | None:
        t = frozenset(rel_tokens)
        if "mask-icon" in t and "icon" not in t:
            return None
        if "apple-touch-icon-precomposed" in t:
            return 30
        if "apple-touch-icon" in t:
            return 20
        if "icon" in t or "shortcut" in t:
            return 0
        return None

    for rel_tokens, href in parser.links:
        if not rel_tokens:
            continue
        pri = _rel_pri(rel_tokens)
        if pri is None:
            continue
        abs_url = urljoin(base_url, href)
        cand = (pri, abs_url)
        if best is None or cand[0] < best[0]:
            best = cand
    return best[1] if best else None


def _get_follow_limited(
    client: httpx.Client, start_url: str, max_read: int
) -> tuple[int, str, bytes, str] | None:
    """GET with manual redirects; SSRF-check each hop. Returns (status, content_type, body, final_url)."""
    cur = start_url
    for _ in range(MAX_REDIRECTS + 1):
        try:
            assert_safe_http_url_for_ssrf(cur)
        except ValueError:
            return None
        r: httpx.Response | None = None
        try:
            req = client.build_request(
                "GET", cur, headers={"User-Agent": "ArchiveConsole/1.0"}
            )
            r = client.send(req, stream=True)
            if r.status_code in (301, 302, 303, 307, 308):
                loc = (r.headers.get("location") or "").strip()
                r.close()
                if not loc:
                    return None
                cur = urljoin(cur, loc)
                continue
            if r.status_code != 200:
                r.close()
                return None
            body = b""
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) >= max_read:
                    break
            ct = r.headers.get("content-type") or ""
            r.close()
            return (200, ct, body[:max_read], cur)
        except httpx.RequestError:
            if r is not None:
                try:
                    r.close()
                except Exception:
                    pass
            return None
        except Exception:
            if r is not None:
                try:
                    r.close()
                except Exception:
                    pass
            return None
    return None


def fetch_bookmark_icon(url: str) -> tuple[bytes, str] | None:
    """
    Fetch favicon bytes for a bookmark page URL. Returns (data, content_type) or None.

    Applies SSRF checks on every request URL (including redirects).
    """
    try:
        norm = normalize_bookmark_url(url)
    except ValueError:
        return None

    parsed = urlparse(norm)
    scheme = parsed.scheme
    netloc = parsed.netloc
    favicon_url = urljoin(f"{scheme}://{netloc}/", "favicon.ico")

    timeout = httpx.Timeout(FETCH_TIMEOUT_SEC, connect=FETCH_TIMEOUT_SEC)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        got = _get_follow_limited(client, favicon_url, ICON_MAX_BYTES)
        if got:
            _st, ct, data, _fu = got
            if _is_probably_image(ct, data):
                return (data, ct or "application/octet-stream")

        page_url = norm
        got2 = _get_follow_limited(client, page_url, HTML_SNIFF_MAX_BYTES)
        if not got2:
            return None
        _st2, _ct2, chunk, final_page = got2
        icon_href = _collect_icon_href_from_html(chunk, final_page)
        if not icon_href:
            return None
        got3 = _get_follow_limited(client, icon_href, ICON_MAX_BYTES)
        if not got3:
            return None
        _st3, ct3, data3, _ifu = got3
        if _is_probably_image(ct3, data3):
            return (data3, ct3 or "application/octet-stream")
    return None
