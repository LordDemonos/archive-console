"""Structured console errors: durable JSON next to report.html + optional global ledger in state."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .paths import PathNotAllowedError, assert_allowed_path

if TYPE_CHECKING:
    from .settings import ConsoleState

logger = logging.getLogger(__name__)

ERRORS_JSON_BASENAME = "archive_console_errors.json"
MAX_ERRORS_PER_FILE = 200
MAX_STDERR_EXCERPT = 2000
MAX_MESSAGE_LEN = 800
MAX_OPERATION_LEN = 200

ErrorStage = Literal["yt-dlp", "galleries-dl", "metadata", "duplicates", "rename", "deepL"]
ErrorSeverity = Literal["error", "warning"]


def utc_iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clip(s: str, n: int) -> str:
    t = (s or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def redact_sensitive_keys(obj: dict[str, Any]) -> dict[str, Any]:
    """Shallow redact for logging / storage (never persist raw cookies or API keys)."""
    out: dict[str, Any] = {}
    for k, v in obj.items():
        lk = str(k).lower()
        if any(
            x in lk
            for x in ("password", "secret", "token", "cookie", "auth", "api_key", "apikey")
        ):
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = redact_sensitive_keys(v)
        else:
            out[k] = v
    return out


def make_error_record(
    *,
    stage: ErrorStage,
    operation: str,
    message: str,
    severity: ErrorSeverity = "error",
    run_id: str | None = None,
    job_id: str | None = None,
    technical: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    retryable: bool = False,
    ts_utc: str | None = None,
) -> dict[str, Any]:
    """Build one JSON-serializable error row (safe for state.json and run folders)."""
    rec: dict[str, Any] = {
        "ts_utc": ts_utc or utc_iso_now(),
        "stage": stage,
        "operation": _clip(str(operation or "unknown"), MAX_OPERATION_LEN),
        "severity": severity,
        "message": _clip(str(message or ""), MAX_MESSAGE_LEN),
        "retryable": bool(retryable),
    }
    if run_id:
        rec["run_id"] = str(run_id)[:64]
    if job_id:
        rec["job_id"] = str(job_id)[:64]
    tech = dict(technical or {})
    if "stderr_excerpt" in tech and isinstance(tech["stderr_excerpt"], str):
        tech["stderr_excerpt"] = _clip(tech["stderr_excerpt"], MAX_STDERR_EXCERPT)
    if "stdout_excerpt" in tech and isinstance(tech["stdout_excerpt"], str):
        tech["stdout_excerpt"] = _clip(tech["stdout_excerpt"], MAX_STDERR_EXCERPT)
    if tech:
        rec["technical"] = tech
    ctx = redact_sensitive_keys(dict(context or {}))
    if ctx:
        rec["context"] = ctx
    return rec


def _resolve_log_folder(
    archive_root: Path,
    log_folder_rel: str,
    allowed_prefixes: list[str],
) -> Path | None:
    rel = (log_folder_rel or "").strip().replace("\\", "/")
    if not rel:
        return None
    root = archive_root.resolve()
    try:
        folder = (root / rel).resolve()
        folder.relative_to(root)
    except (OSError, ValueError):
        return None
    try:
        assert_allowed_path(root, rel, allowed_prefixes)
    except PathNotAllowedError:
        return None
    return folder


def read_errors_for_log_folder(
    archive_root: Path,
    log_folder_rel: str | None,
    allowed_prefixes: list[str],
) -> list[dict[str, Any]]:
    if not log_folder_rel:
        return []
    folder = _resolve_log_folder(archive_root, log_folder_rel, allowed_prefixes)
    if folder is None:
        return []
    path = folder / ERRORS_JSON_BASENAME
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("read_errors_for_log_folder: %s", e)
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict) and isinstance(raw.get("errors"), list):
        return [x for x in raw["errors"] if isinstance(x, dict)]
    return []


def append_errors_to_log_folder(
    archive_root: Path,
    log_folder_rel: str,
    allowed_prefixes: list[str],
    records: list[dict[str, Any]],
) -> None:
    if not records:
        return
    folder = _resolve_log_folder(archive_root, log_folder_rel, allowed_prefixes)
    if folder is None:
        logger.warning(
            "append_errors_to_log_folder: bad or disallowed folder rel=%s",
            log_folder_rel,
        )
        return
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ERRORS_JSON_BASENAME
    existing: list[dict[str, Any]] = []
    if path.is_file():
        try:
            cur = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(cur, list):
                existing = [x for x in cur if isinstance(x, dict)]
            elif isinstance(cur, dict) and isinstance(cur.get("errors"), list):
                existing = [x for x in cur["errors"] if isinstance(x, dict)]
        except (OSError, json.JSONDecodeError):
            existing = []
    merged = existing + list(records)
    merged = merged[-MAX_ERRORS_PER_FILE:]
    try:
        path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("append_errors_to_log_folder write failed: %s", e)


def log_error_record(rec: dict[str, Any]) -> None:
    """Structured server log line (no secrets in rec if callers used make_error_record)."""
    logger.warning(
        "archive_console_error stage=%s op=%s sev=%s msg=%s",
        rec.get("stage"),
        rec.get("operation"),
        rec.get("severity"),
        rec.get("message"),
    )


def persist_error(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    log_folder_rel: str | None,
    record: dict[str, Any],
) -> None:
    """Write to run-folder sidecar when possible; always log."""
    log_error_record(record)
    if log_folder_rel:
        append_errors_to_log_folder(
            archive_root,
            log_folder_rel,
            allowed_prefixes,
            [record],
        )


def record_to_sidecar_or_global(
    *,
    archive_root: Path,
    allowed_prefixes: list[str],
    log_folder_rel: str | None,
    record: dict[str, Any],
    state: ConsoleState,
) -> ConsoleState:
    """Sidecar next to report when folder is known and allowlisted; else global ledger."""
    from .settings import append_global_console_errors

    log_error_record(record)
    rel = (log_folder_rel or "").strip().replace("\\", "/")
    if rel and _resolve_log_folder(archive_root, rel, allowed_prefixes) is not None:
        append_errors_to_log_folder(
            archive_root,
            rel,
            allowed_prefixes,
            [record],
        )
        return state
    return append_global_console_errors(state, [record])


_RE_SAFE_ID = re.compile(r"[^a-zA-Z0-9_-]+")


def errors_section_html(errors: list[dict[str, Any]]) -> str:
    """HTML fragment for /reports/view injection (self-contained styles)."""
    esc = (
        lambda s: str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    style = (
        ".ace-errors{font-family:system-ui,Segoe UI,sans-serif;margin:1.5rem 0;"
        "padding:1rem 1.25rem;border:1px solid #c9d1d9;border-radius:8px;"
        "background:#f6f8fa;}"
        ".ace-errors h2{font-size:1.1rem;margin:0 0 0.75rem;color:#24292f;}"
        ".ace-errors .ace-empty{color:#57606a;font-style:italic;margin:0;}"
        ".ace-errors table{width:100%;border-collapse:collapse;font-size:0.875rem;}"
        ".ace-errors th,.ace-errors td{text-align:left;padding:0.35rem 0.5rem;"
        "vertical-align:top;border-bottom:1px solid #d0d7de;}"
        ".ace-errors th{color:#24292f;background:#eaeef2;}"
        ".ace-err-sev-e{color:#a40e26;font-weight:600;}"
        ".ace-err-sev-w{color:#9a6700;font-weight:600;}"
        ".ace-err-tech{font-size:0.8rem;color:#57606a;white-space:pre-wrap;word-break:break-word;}"
    )
    parts = [
        f'<section id="archive-console-errors" class="archive-console-errors" aria-label="Archive Console errors">',
        f"<style>{style}</style>",
        '<div class="ace-errors">',
        "<h2>Archive Console — Errors</h2>",
    ]
    if not errors:
        parts.append('<p class="ace-empty">No errors recorded for this run.</p>')
    else:
        parts.append("<table><thead><tr>")
        for h in ("Time (UTC)", "Stage", "Severity", "Operation", "Message", "Details"):
            parts.append(f"<th>{esc(h)}</th>")
        parts.append("</tr></thead><tbody>")
        for e in errors:
            sev = str(e.get("severity") or "error")
            sev_cls = "ace-err-sev-w" if sev == "warning" else "ace-err-sev-e"
            tech = e.get("technical")
            tech_s = ""
            if isinstance(tech, dict):
                fragments: list[str] = []
                for k in sorted(tech.keys()):
                    fragments.append(f"{k}={tech[k]}")
                tech_s = _clip("\n".join(fragments), 4000)
            parts.append("<tr>")
            parts.append(f"<td>{esc(e.get('ts_utc', '—'))}</td>")
            parts.append(f"<td>{esc(e.get('stage', '—'))}</td>")
            parts.append(f'<td class="{sev_cls}">{esc(sev)}</td>')
            parts.append(f"<td>{esc(e.get('operation', '—'))}</td>")
            parts.append(f"<td>{esc(e.get('message', ''))}</td>")
            parts.append(f'<td class="ace-err-tech">{esc(tech_s)}</td>')
            parts.append("</tr>")
        parts.append("</tbody></table>")
    parts.append("</div></section>")
    return "\n".join(parts)


def inject_errors_before_body_close(html: str, errors_html: str) -> str:
    lowered = html.lower()
    idx = lowered.rfind("</body>")
    if idx == -1:
        return html + errors_html
    return html[:idx] + errors_html + html[idx:]
