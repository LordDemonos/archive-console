"""Read-only ExifTool JSON (-j -n) via subprocess; no shell."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BAD_EXE_CHARS = re.compile(r"[\r\n;&|<>`\"$]")
EXIFTOOL_DEFAULT_TIMEOUT_SEC = 45.0


def validate_exiftool_exe_setting(raw: str | None) -> str:
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if _BAD_EXE_CHARS.search(s):
        raise ValueError("exiftool_exe must be a single path (no shell metacharacters)")
    if len(s) > 512:
        raise ValueError("exiftool_exe path too long")
    return s


def resolve_exiftool_bin(explicit: str) -> str:
    v = (explicit or "").strip()
    return v if v else "exiftool"


def run_exiftool_json(
    file_path: Path,
    *,
    exiftool_bin: str,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str, str]:
    """
    Run `exiftool -j -n` on one file.
    Returns (first_json_object_or_none, stderr, error_message).
    error_message empty on success.
    """
    fp = file_path.resolve()
    if not fp.is_file():
        return None, "", "not a file"
    cmd = [exiftool_bin, "-j", "-n", "-charset", "filename=UTF8", str(fp)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_sec,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        logger.warning("exiftool timeout for %s", fp.name)
        return None, "", f"exiftool timed out after {timeout_sec:.0f}s"
    except FileNotFoundError:
        return (
            None,
            "",
            f"exiftool executable not found ({exiftool_bin!r}). Set ExifTool path in Settings.",
        )
    except OSError as e:
        logger.warning("exiftool spawn error: %s", e)
        return None, "", f"exiftool failed to start: {e}"

    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        tail = err[-800:] if err else proc.stdout[:400]
        return None, err, f"exiftool exit {proc.returncode}: {tail}"

    raw = (proc.stdout or "").strip()
    if not raw:
        return None, err, "exiftool returned empty output"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, err, f"exiftool JSON parse error: {e}"

    if not isinstance(data, list) or not data:
        return None, err, "exiftool returned no records"

    first = data[0]
    if not isinstance(first, dict):
        return None, err, "exiftool record is not an object"

    return first, err, ""
