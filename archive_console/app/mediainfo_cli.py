"""MediaInfo CLI: validate path, run JSON output, map to a stable DTO."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_BAD_EXE_CHARS = re.compile(r"[\r\n;&|<>`\"$]")

# Operator guard: skip very large files to avoid long runs / memory pressure.
MEDIAINFO_MAX_FILE_BYTES = 64 * 1024 * 1024 * 1024  # 64 GiB
MEDIAINFO_TIMEOUT_SEC = 30.0


def validate_mediainfo_exe_setting(raw: str | None) -> str:
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    if _BAD_EXE_CHARS.search(s):
        raise ValueError("mediainfo_exe must be a single path (no shell metacharacters)")
    if len(s) > 512:
        raise ValueError("mediainfo_exe path too long")
    return s


def resolve_mediainfo_bin(explicit: str) -> str:
    v = (explicit or "").strip()
    return v if v else "mediainfo"


class MediaInfoStreamDto(BaseModel):
    kind: str = ""  # General, Video, Audio, Text, Image, Menu
    codec: str = ""
    width: int | None = None
    height: int | None = None
    frame_rate: str = ""
    chroma_subsampling: str = ""
    scan_type: str = ""
    bitrate: str = ""
    title: str = ""
    language: str = ""
    duration_ms: int | None = None


class MediaInfoDetailsDto(BaseModel):
    container: str = ""
    format_profile: str = ""
    duration_ms: int | None = None
    overall_bitrate: str = ""
    streams: list[MediaInfoStreamDto] = Field(default_factory=list)
    sparse: bool = False


def _int_from_mi(val: Any) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("na", "n/a"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _str_from_mi(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("na", "n/a"):
        return ""
    return s


def parse_mediainfo_json(raw: str) -> MediaInfoDetailsDto:
    """Map MediaInfo --Output=JSON into MediaInfoDetailsDto; tolerates odd shapes."""
    data = json.loads(raw)
    if isinstance(data, dict) and "media" in data:
        data = data["media"]
    tracks = data.get("track") if isinstance(data, dict) else None
    if tracks is None:
        return MediaInfoDetailsDto(sparse=True)
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not isinstance(tracks, list):
        return MediaInfoDetailsDto(sparse=True)

    streams: list[MediaInfoStreamDto] = []
    general_duration: int | None = None
    container = ""
    format_profile = ""
    overall_bitrate = ""

    for t in tracks:
        if not isinstance(t, dict):
            continue
        kind = _str_from_mi(t.get("@type") or t.get("type"))
        if kind.lower() == "general":
            container = _str_from_mi(t.get("Format") or t.get("format"))
            format_profile = _str_from_mi(
                t.get("Format_Profile") or t.get("Format_profile") or t.get("format_profile")
            )
            overall_bitrate = _str_from_mi(
                t.get("OverallBitRate") or t.get("Overall_bit_rate") or t.get("BitRate")
            )
            dur = t.get("Duration") or t.get("duration")
            if dur is not None:
                general_duration = _int_from_mi(dur)
            continue

        st = MediaInfoStreamDto(
            kind=kind or "Unknown",
            codec=_str_from_mi(
                t.get("Format") or t.get("CodecID") or t.get("codec_id")
            ),
            width=_int_from_mi(t.get("Width") or t.get("width")),
            height=_int_from_mi(t.get("Height") or t.get("height")),
            frame_rate=_str_from_mi(
                t.get("FrameRate") or t.get("Frame_rate") or t.get("framerate")
            ),
            chroma_subsampling=_str_from_mi(
                t.get("ChromaSubsampling") or t.get("chroma_subsampling")
            ),
            scan_type=_str_from_mi(t.get("ScanType") or t.get("Scan_type")),
            bitrate=_str_from_mi(t.get("BitRate") or t.get("Bit_rate")),
            title=_str_from_mi(t.get("Title") or t.get("title")),
            language=_str_from_mi(t.get("Language") or t.get("language")),
            duration_ms=_int_from_mi(t.get("Duration") or t.get("duration")),
        )
        streams.append(st)

    duration_ms = general_duration
    if duration_ms is None:
        for s in streams:
            if s.duration_ms is not None:
                duration_ms = s.duration_ms
                break

    sparse = not container and not streams
    return MediaInfoDetailsDto(
        container=container,
        format_profile=format_profile,
        duration_ms=duration_ms,
        overall_bitrate=overall_bitrate,
        streams=streams,
        sparse=sparse,
    )


def run_mediainfo_json_subprocess(
    exe: str,
    file_abs: Path,
    *,
    timeout_sec: float = MEDIAINFO_TIMEOUT_SEC,
) -> tuple[int, str, str]:
    """Run mediainfo --Output=JSON. Returns (returncode, stdout, stderr)."""
    cmd = [exe, "--Output=JSON", str(file_abs)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        return (
            proc.returncode,
            proc.stdout or "",
            proc.stderr or "",
        )
    except subprocess.TimeoutExpired as e:
        partial_out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        partial_err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        return -124, partial_out, partial_err + "\n[timeout]"
    except FileNotFoundError:
        return -127, "", "mediainfo executable not found"
    except OSError as e:
        return -1, "", str(e)


def mediainfo_for_file(
    exe: str,
    file_abs: Path,
    *,
    max_bytes: int = MEDIAINFO_MAX_FILE_BYTES,
    timeout_sec: float = MEDIAINFO_TIMEOUT_SEC,
) -> dict[str, Any]:
    """
    Run MediaInfo and return API-shaped dict: ok, error?, details? (serialized DTO).
    Does not validate allowlist (caller must).
    """
    try:
        st = file_abs.stat()
    except OSError as e:
        return {"ok": False, "error": f"stat failed: {e}"}

    if not file_abs.is_file():
        return {"ok": False, "error": "not a file"}

    if st.st_size > max_bytes:
        return {
            "ok": False,
            "error": f"file larger than {max_bytes} bytes (limit for MediaInfo)",
        }

    code, out, err = run_mediainfo_json_subprocess(
        exe, file_abs, timeout_sec=timeout_sec
    )
    if code == -127:
        return {"ok": False, "error": "MediaInfo not found or not executable"}
    if code == -124:
        return {"ok": False, "error": "MediaInfo timed out"}
    if code != 0:
        tail = (err or out or "unknown error")[-2000:]
        logger.warning("mediainfo nonzero exit=%s", code)
        return {"ok": False, "error": tail.strip() or f"exit code {code}"}

    out_s = (out or "").strip()
    if not out_s:
        return {"ok": False, "error": "empty MediaInfo output"}

    try:
        dto = parse_mediainfo_json(out_s)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"invalid JSON from MediaInfo: {e}"}

    return {"ok": True, "details": dto.model_dump()}
