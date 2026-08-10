"""Parse and serialize yt-dlp.conf — single model in sync with disk."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .yt_dlp_config_model import YtdlpUiModel

OPTION_LONG = re.compile(r"^\s*--([\w-]+)(?:\s+(.*))?\s*$")
OPTION_SHORT = re.compile(r"^\s*-([a-zA-Z])(?:\s+(.*))?\s*$")

# Short flags allowed in yt-dlp.conf per README examples (-o, -P, -f, -S, -x, -w, -c).
SHORT_OPTION_TO_CLI: dict[str, str] = {
    "o": "output",
    "P": "paths",
    "f": "format",
    "S": "format-sort",
    "x": "extract-audio",
    "w": "no-overwrites",
    "c": "continue",
}

# --continue maps to continue_dl; --no-playlist is CLI name (dest noplaylist in yt-dlp).
CLI_TO_ATTR: dict[str, str] = {
    "continue": "continue_dl",
    "no-playlist": "noplaylist",
    "noplaylist": "noplaylist",  # legacy bad serialize — parse only, never emit
}


def strip_conf_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _try_parse_option_line(line: str) -> tuple[str, str] | None:
    m = OPTION_LONG.match(line)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    m2 = OPTION_SHORT.match(line)
    if not m2:
        return None
    letter, rest_g = m2.group(1), (m2.group(2) or "").strip()
    long_opt = SHORT_OPTION_TO_CLI.get(letter)
    if not long_opt:
        return None
    return long_opt, rest_g

SKIP_FIELDS = frozenset({"extra_kv", "preserved_tail"})

_MANAGED_ATTRS: frozenset[str] | None = None


def managed_attrs() -> frozenset[str]:
    global _MANAGED_ATTRS
    if _MANAGED_ATTRS is None:
        _MANAGED_ATTRS = frozenset(
            k for k in YtdlpUiModel.model_fields if k not in SKIP_FIELDS
        )
    return _MANAGED_ATTRS


def cli_to_attr(cli: str) -> str | None:
    if cli in CLI_TO_ATTR:
        return CLI_TO_ATTR[cli]
    cand = cli.replace("-", "_")
    if cand in managed_attrs():
        return cand
    return None


TIER_B_KEY_DENY = re.compile(
    r"(?i)(password|bearer|authorization|secret|session_id|refresh_token)"
)
TIER_B_KEY_ALLOW = re.compile(r"^[a-z][a-z0-9_-]*$", re.I)
MAX_EXTRA_VAL_LEN = 8192

# (model_attr, cli_name, kind: bool|str|int|float)
SERIALIZE_ORDER: list[tuple[str, str, str]] = [
    ("cookies", "cookies", "str"),
    ("cookies_from_browser", "cookies-from-browser", "str"),
    ("force_ipv4", "force-ipv4", "bool"),
    ("sleep_requests", "sleep-requests", "float"),
    ("sleep_interval", "sleep-interval", "float"),
    ("max_sleep_interval", "max-sleep-interval", "float"),
    ("socket_timeout", "socket-timeout", "float"),
    ("retries", "retries", "int"),
    ("fragment_retries", "fragment-retries", "int"),
    ("file_access_retries", "file-access-retries", "int"),
    ("verbose", "verbose", "bool"),
    ("quiet", "quiet", "bool"),
    ("no_warnings", "no-warnings", "bool"),
    ("ignore_errors", "ignore-errors", "bool"),
    ("no_progress", "no-progress", "bool"),
    ("write_thumbnail", "write-thumbnail", "bool"),
    ("write_sub", "write-sub", "bool"),
    ("write_description", "write-description", "bool"),
    ("write_info_json", "write-info-json", "bool"),
    ("write_auto_subs", "write-auto-subs", "bool"),
    ("embed_metadata", "embed-metadata", "bool"),
    ("embed_thumbnail", "embed-thumbnail", "bool"),
    ("embed_subs", "embed-subs", "bool"),
    ("embed_chapters", "embed-chapters", "bool"),
    ("sub_langs", "sub-langs", "str"),
    ("format", "format", "str"),
    ("format_sort", "format-sort", "str"),
    ("merge_output_format", "merge-output-format", "str"),
    ("output", "output", "str"),
    ("paths", "paths", "str"),
    ("no_part", "no-part", "bool"),
    ("no_check_formats", "no-check-formats", "bool"),
    ("remux_video", "remux-video", "str"),
    ("extract_audio", "extract-audio", "bool"),
    ("audio_format", "audio-format", "str"),
    ("sponsorblock_remove", "sponsorblock-remove", "str"),
    ("write_comments", "write-comments", "bool"),
    ("external_downloader", "external-downloader", "str"),
    ("concurrent_fragments", "concurrent-fragments", "int"),
    ("buffer_size", "buffer-size", "str"),
    ("http_chunk_size", "http-chunk-size", "str"),
    ("match_filter", "match-filter", "str"),
    ("extractor_args", "extractor-args", "str"),
    ("js_runtimes", "js-runtimes", "str"),
    ("remote_components", "remote-components", "str"),
    ("noplaylist", "no-playlist", "bool"),
    ("restrict_filenames", "restrict-filenames", "bool"),
    ("no_overwrites", "no-overwrites", "bool"),
    ("continue_dl", "continue", "bool"),
    ("skip_unavailable_fragments", "skip-unavailable-fragments", "bool"),
]

BOOL_ATTRS = {a for a, _, k in SERIALIZE_ORDER if k == "bool"}
INT_ATTRS = {a for a, _, k in SERIALIZE_ORDER if k == "int"}
FLOAT_ATTRS = {a for a, _, k in SERIALIZE_ORDER if k == "float"}


def tier_b_allowed(cli_key: str, val: str) -> bool:
    if not TIER_B_KEY_ALLOW.match(cli_key):
        return False
    if TIER_B_KEY_DENY.search(cli_key):
        return False
    # Tier A options must not appear in extra_kv (avoid split-brain)
    if cli_to_attr(cli_key) is not None:
        return False
    blocked = frozenset({"cookies", "cookies-from-browser"})
    if cli_key.lower() in blocked:
        return False
    if "\n" in val or "\r" in val or "\x00" in val:
        return False
    if len(val) > MAX_EXTRA_VAL_LEN:
        return False
    if re.search(r"[;&`]|\$\(", val):
        return False
    return True


def _fmt_cli_value(val: str) -> str:
    if re.search(r'[\s"#]', val) or val == "":
        inner = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{inner}"'
    return val


def _coerce_value(attr: str, val: str) -> Any:
    if attr in BOOL_ATTRS:
        if not val:
            return True
        return val.lower() in ("1", "true", "yes", "on")
    if attr in INT_ATTRS:
        return int(float(val))
    if attr in FLOAT_ATTRS:
        return float(val)
    return val


def parse_conf_with_report(text: str) -> tuple[YtdlpUiModel, list[str]]:
    text = strip_conf_bom(text)
    preserved: list[str] = []
    field_updates: dict[str, Any] = {}
    extra: dict[str, str] = {}
    warnings: list[str] = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        raw = line
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            preserved.append(raw)
            continue
        parsed = _try_parse_option_line(line)
        if parsed is None:
            sm = OPTION_SHORT.match(line)
            if sm:
                ch = sm.group(1)
                warnings.append(
                    f"Line {lineno}: short option -{ch} is not supported by this "
                    "parser (use the long --form); line kept verbatim."
                )
            preserved.append(raw)
            continue
        opt, rest = parsed
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        elif rest.startswith("'") and rest.endswith("'"):
            rest = rest[1:-1]

        attr = cli_to_attr(opt)
        if attr:
            if not rest and attr not in BOOL_ATTRS:
                preserved.append(raw)
                continue
            try:
                field_updates[attr] = _coerce_value(attr, rest)
            except (TypeError, ValueError):
                warnings.append(
                    f"Line {lineno}: could not parse --{opt} value; "
                    "line kept in preserved tail."
                )
                preserved.append(raw)
            continue
        if tier_b_allowed(opt, rest):
            extra[opt] = rest
        else:
            preserved.append(raw)

    base = YtdlpUiModel().model_dump()
    base.update(field_updates)
    base["extra_kv"] = extra
    tail = "\n".join(preserved)
    if tail:
        tail = tail.rstrip() + "\n"
    base["preserved_tail"] = tail
    return YtdlpUiModel.model_validate(base), warnings


def parse_conf(text: str) -> YtdlpUiModel:
    m, _ = parse_conf_with_report(text)
    return m


def _rest_unquoted(rest: str) -> str:
    if rest.startswith('"') and rest.endswith('"'):
        return rest[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if rest.startswith("'") and rest.endswith("'"):
        return rest[1:-1]
    return rest


def _should_omit_managed_scalar(model: YtdlpUiModel, attr: str, val: Any) -> bool:
    if val is None or val == "":
        return True
    if attr == "max_sleep_interval":
        fval = float(val)
        if fval <= 0:
            return True
        if model.sleep_interval is not None and fval < float(model.sleep_interval):
            return True
    return False


def _conf_option_lines_to_argv(content: str) -> list[str]:
    argv: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("--") or stripped.startswith("#"):
            continue
        parsed = _try_parse_option_line(line)
        if parsed is None:
            continue
        opt, rest = parsed
        argv.append(f"--{opt}")
        if rest:
            argv.append(_rest_unquoted(rest))
    return argv


def serialize_conf(
    model: YtdlpUiModel,
    *,
    preset_id: str,
    human_note: str = "",
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"# Generated by Archive Console — last saved {now} — preset: {preset_id}",
    ]
    if human_note.strip():
        lines.append("# " + human_note.strip().replace("\n", "\n# "))
    lines.extend(
        [
            "# Managed flags (deterministic order). User comments and non-managed lines are in preserved_tail below.",
            "",
        ]
    )
    for attr, cli, kind in SERIALIZE_ORDER:
        val = getattr(model, attr)
        if kind == "bool":
            if val:
                lines.append(f"--{cli}")
            continue
        if _should_omit_managed_scalar(model, attr, val):
            continue
        if kind == "int":
            lines.append(f"--{cli} {int(val)}")
        elif kind == "float":
            lines.append(f"--{cli} {float(val)}")
        else:
            lines.append(f"--{cli} {_fmt_cli_value(str(val))}")
    for k in sorted(model.extra_kv.keys()):
        v = model.extra_kv[k]
        if v == "":
            lines.append(f"--{k}")
        else:
            lines.append(f"--{k} {_fmt_cli_value(v)}")
    body = "\n".join(lines).rstrip() + "\n"
    tail = (model.preserved_tail or "").strip()
    if tail:
        body = body.rstrip() + "\n\n" + tail.rstrip() + "\n"
    return body


def preview_cli(model: YtdlpUiModel, *, max_len: int = 12000) -> str:
    chunks: list[str] = ["yt-dlp"]
    for attr, cli, kind in SERIALIZE_ORDER:
        val = getattr(model, attr)
        if kind == "bool":
            if val:
                chunks.append(f"--{cli}")
            continue
        if _should_omit_managed_scalar(model, attr, val):
            continue
        if kind in ("int", "float"):
            chunks.append(f"--{cli}")
            chunks.append(str(val))
        else:
            chunks.append(f"--{cli}")
            chunks.append(_fmt_cli_value(str(val)))
    for k in sorted(model.extra_kv.keys()):
        v = model.extra_kv[k]
        chunks.append(f"--{k}" if v == "" else f"--{k}")
        if v:
            chunks.append(_fmt_cli_value(v))
    s = " ".join(chunks)
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


_PROBE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _probe_ytdlp_cli_argv(argv: list[str]) -> str | None:
    """Return a short error if yt-dlp rejects argv (full option validation), else None."""
    try:
        from yt_dlp import parse_options

        parse_options(argv + [_PROBE_URL])
        return None
    except Exception as ex:
        msg = str(ex).strip()
        if not msg:
            return type(ex).__name__
        for line in reversed(msg.splitlines()):
            stripped = line.strip()
            if stripped and not stripped.startswith("Usage:"):
                return stripped
        return msg.splitlines()[-1].strip() if msg.splitlines() else msg


def _probe_unknown_ytdlp_option(argv: list[str]) -> str | None:
    """Line-level check for unrecognized long options."""
    try:
        from yt_dlp.options import parseOpts

        parseOpts(argv + [_PROBE_URL])
        return None
    except Exception as ex:
        msg = str(ex).lower()
        if "no such option" in msg:
            tail = str(ex).strip().splitlines()
            return tail[-1] if tail else str(ex)
        return None


def rejected_ytdlp_cli_options(content: str) -> list[str]:
    """
    Validate managed ``--long-opt`` lines against yt-dlp (unknown flags and
    cross-option rules such as max-sleep-interval vs sleep-interval).
    """
    argv = _conf_option_lines_to_argv(content)
    if argv:
        err = _probe_ytdlp_cli_argv(argv)
        if err:
            return [f"yt-dlp.conf: {err}"]
    bad: list[str] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("--") or stripped.startswith("#"):
            continue
        parsed = _try_parse_option_line(line)
        if parsed is None:
            continue
        opt, rest = parsed
        opt_argv = [f"--{opt}"]
        if rest:
            opt_argv.append(_rest_unquoted(rest))
        err = _probe_unknown_ytdlp_option(opt_argv)
        if err:
            bad.append(f"Line {lineno}: --{opt} — {err}")
    return bad


def rejected_ytdlp_model_cli_options(model: YtdlpUiModel) -> list[str]:
    """Validate serialized Tier A + Tier B options from a model."""
    return rejected_ytdlp_cli_options(serialize_conf(model, preset_id="validate"))


def extract_generated_banner_info(text: str) -> tuple[bool, str | None]:
    """Detect Console-generated header; return (has_banner, preset_id or None)."""
    for line in text.splitlines()[:8]:
        if "Generated by Archive Console" in line and "preset:" in line:
            part = line.split("preset:", 1)[-1].strip()
            return True, part
    return False, None
