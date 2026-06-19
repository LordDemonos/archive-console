"""
Run ``czkawka_cli`` on the Archive Console host (operator-selected absolute paths).

Scans are read-only: we never pass delete flags. Results come from ``--pretty-file-to-save``
JSON when the tool supports it (duplicate hash mode uses a size-keyed schema).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from .settings import ConsoleState

logger = logging.getLogger(__name__)

ScanMode = Literal["dup", "image", "empty-folders", "big", "empty-files", "video"]
DupMethod = Literal["HASH", "SIZE", "NAME"]
HashType = Literal["BLAKE3", "CRC32", "XXH3"]

SCAN_MODES: frozenset[str] = frozenset(
    {"dup", "image", "empty-folders", "big", "empty-files", "video"}
)
DUP_METHODS: frozenset[str] = frozenset({"HASH", "SIZE", "NAME"})
HASH_TYPES: frozenset[str] = frozenset({"BLAKE3", "CRC32", "XXH3"})
EXTENSION_MACROS: frozenset[str] = frozenset({"IMAGE", "VIDEO", "TEXT", "MUSIC"})

_BAD_EXE_CHARS = re.compile(r"[\r\n;&|<>`\"$]")


def validate_czkawka_exe_setting(raw: str | None) -> str:
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if _BAD_EXE_CHARS.search(s):
        raise ValueError("czkawka_exe must be a single path (no shell metacharacters)")
    if len(s) > 512:
        raise ValueError("czkawka_exe path too long")
    return s


def resolve_czkawka_bin(st: ConsoleState) -> str:
    explicit = (getattr(st, "czkawka_exe", None) or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return str(p.resolve())
        return explicit
    for name in (
        "czkawka_cli",
        "czkawka",
        "czkawka_cli.exe",
        "czkawka.exe",
        "windows_czkawka_cli",
        "windows_czkawka_cli.exe",
    ):
        found = shutil.which(name)
        if found:
            return found
    return "czkawka_cli"


def czkawka_invocable(exe: str) -> bool:
    if not exe or not exe.strip():
        return False
    p = Path(exe)
    if p.is_file():
        return True
    return shutil.which(exe) is not None


def validate_host_directory(raw: str) -> Path:
    s = (raw or "").strip().strip('"')
    if not s:
        raise ValueError("directory path cannot be empty")
    if "\0" in s:
        raise ValueError("invalid directory path")
    try:
        p = Path(s).expanduser().resolve()
    except OSError as e:
        raise ValueError(f"invalid directory path: {e}") from e
    if not p.is_dir():
        raise ValueError(f"not a directory: {p}")
    return p


def normalize_dup_json(raw: Any) -> dict[str, Any]:
    """Turn czkawka dup JSON (size -> list of hash groups) into UI-friendly groups."""
    groups: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return {"group_count": 0, "groups": [], "parse": "empty"}
    for size_key, bucket in raw.items():
        if not isinstance(bucket, list):
            continue
        for idx, files in enumerate(bucket):
            if not isinstance(files, list) or len(files) < 2:
                continue
            norm_files: list[dict[str, Any]] = []
            for item in files:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if not path:
                    continue
                norm_files.append(
                    {
                        "path": str(path),
                        "size": item.get("size"),
                        "hash": item.get("hash"),
                        "modified_date": item.get("modified_date"),
                    }
                )
            if len(norm_files) >= 2:
                groups.append(
                    {
                        "group_id": f"{size_key}_{idx}",
                        "size_bytes": int(size_key) if str(size_key).isdigit() else None,
                        "files": norm_files,
                    }
                )
    return {"group_count": len(groups), "groups": groups, "parse": "dup"}


def normalize_generic_json(raw: Any, *, mode: str) -> dict[str, Any]:
    """Best-effort summary when mode JSON is not the dup schema."""
    if isinstance(raw, list):
        return {
            "group_count": len(raw),
            "groups": [],
            "parse": "list",
            "list_length": len(raw),
        }
    if isinstance(raw, dict):
        dup_try = normalize_dup_json(raw)
        if dup_try["group_count"] > 0:
            return dup_try
        return {
            "group_count": 0,
            "groups": [],
            "parse": "object",
            "top_level_keys": list(raw.keys())[:40],
        }
    return {"group_count": 0, "groups": [], "parse": "unknown", "mode": mode}


def build_czkawka_argv(
    *,
    exe: str,
    mode: ScanMode,
    directories: list[Path],
    exclude_directories: list[Path],
    json_out: Path,
    dup_method: DupMethod = "HASH",
    hash_type: HashType = "BLAKE3",
    minimal_file_size: int = 1024,
    extension_macros: list[str] | None = None,
    number_of_big_files: int = 50,
) -> list[str]:
    if mode not in SCAN_MODES:
        raise ValueError(f"unsupported scan mode: {mode}")
    if not directories:
        raise ValueError("at least one directory is required")
    cmd: list[str] = [exe, mode]
    for d in directories:
        cmd.extend(["-d", str(d)])
    for e in exclude_directories:
        cmd.extend(["-e", str(e)])
    if extension_macros:
        for macro in extension_macros:
            cmd.extend(["-x", macro])
    if mode == "dup":
        cmd.extend(["-s", dup_method, "-t", hash_type])
        if minimal_file_size > 0:
            cmd.extend(["-m", str(int(minimal_file_size))])
    if mode == "big":
        cmd.extend(["-n", str(max(1, min(number_of_big_files, 10_000)))])
    cmd.extend(
        [
            "-N",
            "-M",
            "-W",
            "--pretty-file-to-save",
            str(json_out),
        ]
    )
    return cmd


def run_czkawka_subprocess(argv: list[str]) -> subprocess.CompletedProcess[str]:
    logger.info("czkawka scan argv0=%s mode=%s", argv[0] if argv else "", argv[1] if len(argv) > 1 else "")
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )


def load_and_normalize_results(json_path: Path, *, mode: str) -> dict[str, Any]:
    if not json_path.is_file():
        return {
            "group_count": 0,
            "groups": [],
            "parse": "missing_json",
            "json_path": str(json_path),
        }
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {
            "group_count": 0,
            "groups": [],
            "parse": "json_error",
            "error": str(e),
        }
    if mode == "dup":
        out = normalize_dup_json(raw)
    else:
        out = normalize_generic_json(raw, mode=mode)
    out["raw_json_bytes"] = json_path.stat().st_size if json_path.is_file() else 0
    return out
