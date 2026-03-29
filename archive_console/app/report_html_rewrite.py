"""Rewrite file:// links in report HTML to same-origin /reports/file URLs for Archive Console."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .paths import is_allowed

# href="file:///..." or src="file:..."
_ATTR_FILE_URI = re.compile(
    r'(?P<pre>\b(?:href|src)\s*=\s*)(?P<q>["\'])(?P<uri>file:[^"\']+)(?P=q)',
    re.I,
)


def file_url_to_path(url: str) -> Path | None:
    """Best-effort file: URL → local Path (resolved). Unsupported forms return None."""
    s = (url or "").strip()
    if not s.lower().startswith("file:"):
        return None
    try:
        parsed = urlparse(s)
    except ValueError:
        return None
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path or "")
    if os.name == "nt":
        # file:///E:/dir/file → pathname /E:/dir/file
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        # UNC remains //server/share — resolve() may still map under archive_root
    else:
        path = path or "/"
    try:
        return Path(path).expanduser().resolve()
    except (OSError, ValueError):
        return None


def _rel_reports_file_url(rel_posix: str) -> str:
    return f"/reports/file?rel={quote(rel_posix, safe='')}"


def path_to_allowed_rel(
    full: Path,
    archive_root: Path,
    allowed_prefixes: list[str],
) -> str | None:
    root = archive_root.resolve()
    try:
        resolved = full.resolve()
    except (OSError, ValueError):
        return None
    if not is_allowed(root, resolved, allowed_prefixes):
        return None
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return None


def rewrite_file_attributes(
    html: str,
    archive_root: Path,
    allowed_prefixes: list[str],
) -> str:
    root = archive_root.resolve()

    def repl(m: re.Match[str]) -> str:
        uri = m.group("uri")
        p = file_url_to_path(uri)
        if p is None:
            return m.group(0)
        rel = path_to_allowed_rel(p, root, allowed_prefixes)
        if rel is None:
            return m.group(0)
        q = m.group("q")
        return f'{m.group("pre")}{q}{_rel_reports_file_url(rel)}{q}'

    return _ATTR_FILE_URI.sub(repl, html)


def _viewer_shim_js(archive_root: Path) -> str:
    root_lit = json.dumps(archive_root.resolve().as_posix())
    return f"""(function () {{
  try {{
    if (location.protocol === "file:") return;
  }} catch (e) {{
    return;
  }}
  var ROOT = {root_lit};
  function norm(p) {{
    return String(p || "").replace(/\\\\/g, "/");
  }}
  function pathFromFileUrl(href) {{
    try {{
      var u = new URL(href);
      if (u.protocol !== "file:") return null;
      var p = decodeURIComponent(u.pathname || "");
      if (p.length >= 3 && p.charAt(0) === "/" && p.charAt(2) === ":") {{
        p = p.substring(1);
      }}
      return norm(p);
    }} catch (e) {{
      return null;
    }}
  }}
  function toRel(absPathNorm) {{
    var abs = norm(absPathNorm);
    var rootNorm = norm(ROOT);
    var lowA = abs.toLowerCase();
    var lowR = rootNorm.toLowerCase();
    if (lowA === lowR) return "";
    if (!lowA.startsWith(lowR + "/")) return null;
    return abs.slice(rootNorm.length + 1);
  }}
  function navigate(e, rel) {{
    var url = "/reports/file?rel=" + encodeURIComponent(rel.replace(/\\\\/g, "/"));
    if (e.type === "auxclick" && e.button === 1) {{
      e.preventDefault();
      window.open(url, "_blank", "noopener,noreferrer");
      return;
    }}
    if (e.ctrlKey || e.metaKey) {{
      e.preventDefault();
      window.open(url, "_blank", "noopener,noreferrer");
      return;
    }}
    e.preventDefault();
    if (!e.shiftKey) {{
      window.location.href = url;
    }} else {{
      window.open(url, "_blank", "noopener,noreferrer");
    }}
  }}
  function onPointer(e) {{
    var a = e.target && e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    var hrefAttr = a.getAttribute("href") || "";
    if (!hrefAttr.toLowerCase().startsWith("file:")) return;
    var p = pathFromFileUrl(a.href);
    if (!p) return;
    var rel = toRel(p);
    if (rel == null) return;
    navigate(e, rel);
  }}
  document.addEventListener("click", onPointer, true);
  document.addEventListener("auxclick", onPointer, true);
}})();
"""


def inject_viewer_shim(html: str, archive_root: Path) -> str:
    """Insert shim after <head> open so file: links from JS work on http://127.0.0.1."""
    shim = (
        '<script id="archive-console-viewer-shim">'
        + _viewer_shim_js(archive_root)
        + "</script>"
    )
    lowered = html.lower()
    idx = lowered.find("<head>")
    if idx != -1:
        ins = idx + len("<head>")
        return html[:ins] + shim + html[ins:]
    idx = lowered.find("<html")
    if idx != -1:
        end = html.find(">", idx)
        if end != -1:
            return html[: end + 1] + shim + html[end + 1 :]
    return shim + html


def rewrite_report_html(
    html: str,
    archive_root: Path,
    allowed_prefixes: list[str],
) -> str:
    out = rewrite_file_attributes(html, archive_root, allowed_prefixes)
    return inject_viewer_shim(out, archive_root)
