"""One-off argv: config-locations must not treat overlay path as a URL."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import archive_oneoff_run as oneoff


def test_build_argv_oneoff_uses_separate_config_location_flags() -> None:
    argv = oneoff._build_argv_oneoff(str(ROOT))
    assert argv.count("--config-locations") == 2
    i0 = argv.index("--config-locations")
    i1 = argv.index("--config-locations", i0 + 1)
    oneoff_path = argv[i0 + 1]
    batch_path = argv[i1 + 1]
    assert oneoff_path.endswith("yt-dlp-oneoff.conf")
    assert batch_path.endswith("yt-dlp.conf")


def test_parse_options_does_not_treat_oneoff_conf_as_url() -> None:
    import yt_dlp

    argv = oneoff._build_argv_oneoff(str(ROOT)) + [
        "--simulate",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    po = yt_dlp.parse_options(argv)
    assert po.urls == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    fmt = str(po.ydl_opts.get("format") or "")
    assert "bestaudio" in fmt
