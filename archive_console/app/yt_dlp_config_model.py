"""Single source of truth for yt-dlp.conf UI — Tier A fields + Tier B extra_kv + preserved_tail."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --- Tier A: curated options (serialize order defined in yt_dlp_conf_io) ---


class YtdlpUiModel(BaseModel):
    """Managed fields mirrored to/from yt-dlp.conf (Tier A)."""

    format: str | None = None
    format_sort: str | None = None
    merge_output_format: str | None = None
    output: str | None = None
    paths: str | None = None
    no_part: bool = False
    sleep_requests: float | None = None
    sleep_interval: float | None = None
    max_sleep_interval: float | None = None
    retries: int | None = None
    fragment_retries: int | None = None
    file_access_retries: int | None = None
    force_ipv4: bool = False
    verbose: bool = False
    ignore_errors: bool = False
    write_thumbnail: bool = False
    write_sub: bool = False
    write_description: bool = False
    write_info_json: bool = False
    embed_metadata: bool = False
    embed_thumbnail: bool = False
    embed_subs: bool = False
    embed_chapters: bool = False
    external_downloader: str | None = None
    concurrent_fragments: int | None = None
    match_filter: str | None = None
    no_check_formats: bool = False
    remux_video: str | None = None
    extract_audio: bool = False
    audio_format: str | None = None
    sub_langs: str | None = None
    write_auto_subs: bool = False
    write_comments: bool = False
    sponsorblock_remove: str | None = None
    cookies: str | None = None
    cookies_from_browser: str | None = None
    extractor_args: str | None = None
    js_runtimes: str | None = None
    remote_components: str | None = None
    noplaylist: bool = False
    restrict_filenames: bool = False
    no_overwrites: bool = False
    continue_dl: bool = False
    skip_unavailable_fragments: bool = False
    no_warnings: bool = False
    quiet: bool = False
    no_progress: bool = False
    concurrent_downloads: int | None = None
    buffer_size: str | None = None
    http_chunk_size: str | None = None

    extra_kv: dict[str, str] = Field(default_factory=dict)
    """Tier B: hyphenated yt-dlp option name (no leading --) -> value; empty string = flag."""

    preserved_tail: str = ""
    """Non-option lines from the original file (comments, blanks); appended verbatim on save."""

    model_config = ConfigDict(extra="forbid")


def model_from_dict(data: dict[str, Any]) -> YtdlpUiModel:
    return YtdlpUiModel.model_validate(data)


DOC_ROOT = "https://github.com/yt-dlp/yt-dlp/blob/master/README.md"

TIER_A_GROUPS: list[dict[str, Any]] = [
    {
        "id": "output_paths",
        "label": "Output & filesystem",
        "doc": (
            "Maps to official filesystem options (-o / --output, -P / --paths). "
            "Use %(field)s templates as in yt-dlp OUTPUT TEMPLATE docs."
        ),
        "fields": [
            {
                "key": "output",
                "label": "Output template (-o)",
                "widget": "textarea",
                "rows": 2,
                "placeholder": '%(title)s.%(ext)s or %(uploader)s/%(title)s.%(ext)s',
                "help": (
                    "Filename pattern for downloaded files. Required for per-channel folders. "
                    "Avoid hard-coding .mp4 extension alone — use %(ext)s."
                ),
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "paths",
                "label": "Paths (-P)",
                "widget": "text",
                "placeholder": "home:REL or temp:REL (see docs)",
                "help": (
                    "Where to place home/temp/intermediate files (TYPE:PATH). "
                    "Ignored if --output is an absolute path."
                ),
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "no_part",
                "label": "no-part",
                "widget": "toggle",
                "help": (
                    "Write directly to the final file instead of using .part fragments "
                    "(less safe if interrupted)."
                ),
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
        ],
    },
    {
        "id": "formats",
        "label": "Formats & merge",
        "doc": (
            "-f / --format selects streams; --format-sort (-S) changes “best” ordering. "
            "See ARCHIVE_PLAYLIST_RUN_LOGS.txt for playlist-specific notes."
        ),
        "fields": [
            {
                "key": "format_preset",
                "label": "Format goal",
                "widget": "format_preset",
            },
            {
                "key": "format",
                "label": "Format string (-f / custom)",
                "widget": "textarea",
                "rows": 2,
                "help": (
                    "Format selector: fallback chain of streams to download (video+audio merge, "
                    "progressive, etc.)."
                ),
                "doc_url": f"{DOC_ROOT}#format-selection",
            },
            {
                "key": "format_sort",
                "label": "Format sort (-S)",
                "widget": "text",
                "placeholder": "res:1080,codec,br",
                "help": (
                    "Overrides how yt-dlp ranks formats when using “best”. "
                    "Example: cap resolution or prefer codecs."
                ),
                "doc_url": f"{DOC_ROOT}#sorting-formats",
            },
            {
                "key": "merge_output_format",
                "label": "merge-output-format",
                "widget": "select",
                "choices": ["mkv", "mp4", "webm", "avi"],
                "help": (
                    "Container for merged video+audio (DASH). mkv tolerates mixed codecs "
                    "better than mp4."
                ),
                "doc_url": f"{DOC_ROOT}#video-format-options",
            },
            {
                "key": "no_check_formats",
                "label": "no-check-formats",
                "widget": "toggle",
                "help": (
                    "Skips per-format probe downloads. Useful when probes fail on YouTube "
                    "but a real download would succeed (see your repo yt-dlp.conf notes)."
                ),
                "doc_url": f"{DOC_ROOT}#video-format-options",
            },
            {
                "key": "remux_video",
                "label": "remux-video",
                "widget": "text",
                "placeholder": "(optional codec list)",
                "help": "Remux video to a codec/container after download (needs ffmpeg).",
                "doc_url": f"{DOC_ROOT}#post-processing-options",
            },
            {
                "key": "extract_audio",
                "label": "extract-audio (-x)",
                "widget": "toggle",
                "help": "Download audio only (often paired with --audio-format).",
                "doc_url": f"{DOC_ROOT}#post-processing-options",
            },
            {
                "key": "audio_format",
                "label": "audio-format",
                "widget": "text",
                "placeholder": "mp3 / m4a / opus",
                "help": "Destination codec when post-processing audio.",
                "doc_url": f"{DOC_ROOT}#post-processing-options",
            },
        ],
    },
    {
        "id": "sleep",
        "label": "Sleep & rate limits",
        "doc": "Pause between HTTP requests / entries to reduce 429 rate limits (Download options).",
        "fields": [
            {
                "key": "sleep_requests",
                "label": "sleep-requests (s)",
                "widget": "range",
                "min": 0,
                "max": 30,
                "step": 0.5,
                "help": "Seconds to sleep before each http request.",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "sleep_interval",
                "label": "sleep-interval (s)",
                "widget": "range",
                "min": 0,
                "max": 60,
                "step": 0.5,
                "help": "Seconds to sleep between downloads (playlist/channel).",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "max_sleep_interval",
                "label": "max-sleep-interval (s)",
                "widget": "range",
                "min": 0,
                "max": 120,
                "step": 1,
                "help": "Upper cap when yt-dlp applies adaptive sleep.",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
        ],
    },
    {
        "id": "retries",
        "label": "Retries, throughput & buffers",
        "doc": "Resilience and parallel fragment / file I/O tuning.",
        "fields": [
            {
                "key": "retries",
                "label": "retries",
                "widget": "range",
                "min": 0,
                "max": 50,
                "step": 1,
                "help": "Retries on failed HTTP segments (not only fragments).",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "fragment_retries",
                "label": "fragment-retries",
                "widget": "range",
                "min": 0,
                "max": 50,
                "step": 1,
                "help": "Retries for DASH/HLS fragment failures.",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "file_access_retries",
                "label": "file-access-retries",
                "widget": "range",
                "min": 0,
                "max": 50,
                "step": 1,
                "help": "Retries when the file is temporarily locked on disk.",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "concurrent_fragments",
                "label": "concurrent-fragments",
                "widget": "range",
                "min": 1,
                "max": 32,
                "step": 1,
                "help": "Parallel fragment downloads per file (higher = faster, more aggressive).",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "concurrent_downloads",
                "label": "concurrent-downloads",
                "widget": "range",
                "min": 1,
                "max": 8,
                "step": 1,
                "help": "How many media files can download at once.",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "buffer_size",
                "label": "buffer-size",
                "widget": "text",
                "placeholder": "e.g. 16K",
                "help": "Download buffer size (suffixes like K/M).",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
            {
                "key": "http_chunk_size",
                "label": "http-chunk-size",
                "widget": "text",
                "placeholder": "e.g. 10M",
                "help": "Size of each http chunk (some servers cap this).",
                "doc_url": f"{DOC_ROOT}#download-options",
            },
        ],
    },
    {
        "id": "downloaders",
        "label": "Downloaders",
        "fields": [
            {
                "key": "external_downloader",
                "label": "external-downloader",
                "widget": "select",
                "choices": ["", "aria2c", "ffmpeg", "curl", "wget"],
                "help": (
                    "Delegate HTTP to aria2c/ffmpeg/etc. When set, ensure the tool is "
                    "installed and on PATH."
                ),
                "doc_url": f"{DOC_ROOT}#download-options",
            },
        ],
    },
    {
        "id": "youtube",
        "label": "YouTube / extractor",
        "doc": (
            "Extractor-specific flags (player_client, etc.). "
            "Cookie *paths* belong under Cookies — never paste tokens into Tier B."
        ),
        "fields": [
            {
                "key": "extractor_args",
                "label": "extractor-args",
                "widget": "textarea",
                "rows": 2,
                "placeholder": "youtube:player_client=tv,web_safari,mweb",
                "help": "Per-extractor key:value pairs (see EXTRACTOR ARGUMENTS in yt-dlp README).",
                "doc_url": f"{DOC_ROOT}#extractor-arguments",
            },
            {
                "key": "js_runtimes",
                "label": "js-runtimes",
                "widget": "text",
                "placeholder": "node",
                "help": "External JS runtimes for YouTube n/EJS challenges (often node or deno).",
                "doc_url": "https://github.com/yt-dlp/yt-dlp/wiki/EJS",
            },
            {
                "key": "remote_components",
                "label": "remote-components",
                "widget": "text",
                "placeholder": "ejs:github",
                "help": "Fetch solver components remotely when not bundled (see EJS wiki).",
                "doc_url": "https://github.com/yt-dlp/yt-dlp/wiki/EJS",
            },
            {
                "key": "match_filter",
                "label": "match-filter",
                "widget": "text",
                "placeholder": "!is_live",
                "help": "Skip entries that match this expression (e.g. block live streams).",
                "doc_url": f"{DOC_ROOT}#video-selection",
            },
        ],
    },
    {
        "id": "cookies_paths",
        "label": "Cookies (paths only)",
        "doc": (
            "Only file paths or browser names — never paste cookie file contents here. "
            "Edit cookies.txt under Inputs & config."
        ),
        "fields": [
            {
                "key": "cookies",
                "label": "--cookies path",
                "widget": "text",
                "placeholder": "cookies.txt",
                "help": "Netscape-format cookies file relative to the working directory.",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "cookies_from_browser",
                "label": "cookies-from-browser",
                "widget": "text",
                "placeholder": "chrome / firefox / edge…",
                "help": "Live session from a browser profile (see README for PROFILE syntax).",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
        ],
    },
    {
        "id": "network",
        "label": "Network",
        "doc": "Connectivity workarounds (see Network / Geo sections in README).",
        "fields": [
            {
                "key": "force_ipv4",
                "label": "force-ipv4",
                "widget": "toggle",
                "help": "Avoid IPv6 routes that some CDNs throttle harder than IPv4.",
                "doc_url": f"{DOC_ROOT}#network-options",
            },
        ],
    },
    {
        "id": "metadata_subs",
        "label": "Metadata, subtitles & sidecars",
        "doc": "Sidecar files and embedding into media containers.",
        "fields": [
            {
                "key": "write_thumbnail",
                "label": "write-thumbnail",
                "widget": "toggle",
                "help": "Save cover art next to the media file.",
                "doc_url": f"{DOC_ROOT}#thumbnail-options",
            },
            {
                "key": "write_sub",
                "label": "write-sub",
                "widget": "toggle",
                "help": "Save subtitle files (see sub-langs).",
                "doc_url": f"{DOC_ROOT}#subtitle-options",
            },
            {
                "key": "write_description",
                "label": "write-description",
                "widget": "toggle",
                "help": "Save video description to a .description file.",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "write_info_json",
                "label": "write-info-json",
                "widget": "toggle",
                "help": "Save full metadata JSON (may include personal fields).",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "embed_metadata",
                "label": "embed-metadata",
                "widget": "toggle",
                "help": "Write tags into the media container.",
                "doc_url": f"{DOC_ROOT}#post-processing-options",
            },
            {
                "key": "embed_thumbnail",
                "label": "embed-thumbnail",
                "widget": "toggle",
                "help": "Embed thumbnail as cover art (depends on format).",
                "doc_url": f"{DOC_ROOT}#thumbnail-options",
            },
            {
                "key": "embed_subs",
                "label": "embed-subs",
                "widget": "toggle",
                "help": "Mux subtitles into the output file.",
                "doc_url": f"{DOC_ROOT}#subtitle-options",
            },
            {
                "key": "embed_chapters",
                "label": "embed-chapters",
                "widget": "toggle",
                "help": "Write chapter markers into the media file (e.g. from description).",
                "doc_url": f"{DOC_ROOT}#post-processing-options",
            },
            {
                "key": "sub_langs",
                "label": "sub-langs",
                "widget": "text",
                "placeholder": "en.*, all or alld",
                "help": "Which subtitle languages to fetch (comma list or special tokens).",
                "doc_url": f"{DOC_ROOT}#subtitle-options",
            },
            {
                "key": "write_auto_subs",
                "label": "write-auto-subs",
                "widget": "toggle",
                "help": "Also download auto-generated / translated captions (slower).",
                "doc_url": f"{DOC_ROOT}#subtitle-options",
            },
            {
                "key": "write_comments",
                "label": "write-comments",
                "widget": "toggle",
                "help": "Fetch comments when the extractor supports it (can be slow).",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
        ],
    },
    {
        "id": "sponsorblock",
        "label": "SponsorBlock",
        "doc": (
            "Categories like sponsor, intro, outro, selfpromo — see SponsorBlock options "
            "in README. Tier A exposes removal only; use Tier B for --sponsorblock-mark."
        ),
        "fields": [
            {
                "key": "sponsorblock_remove",
                "label": "sponsorblock-remove",
                "widget": "text",
                "placeholder": "all or sponsor,intro",
                "help": (
                    "Segments to cut from the final file (requires ffmpeg). "
                    "Use empty to omit the option."
                ),
                "doc_url": f"{DOC_ROOT}#sponsorblock-options",
            },
        ],
    },
    {
        "id": "behavior",
        "label": "Logging & general behavior",
        "doc": "Verbosity, playlist handling, resume / overwrite policy.",
        "fields": [
            {
                "key": "verbose",
                "label": "verbose",
                "widget": "toggle",
                "help": "Detailed stderr progress (good for troubleshooting).",
                "doc_url": f"{DOC_ROOT}#verbosity-and-simulation-options",
            },
            {
                "key": "quiet",
                "label": "quiet",
                "widget": "toggle",
                "help": "Less console output (mutually exclusive with verbose for most users).",
                "doc_url": f"{DOC_ROOT}#verbosity-and-simulation-options",
            },
            {
                "key": "no_warnings",
                "label": "no-warnings",
                "widget": "toggle",
                "help": "Hide warning lines on stderr.",
                "doc_url": f"{DOC_ROOT}#verbosity-and-simulation-options",
            },
            {
                "key": "no_progress",
                "label": "no-progress",
                "widget": "toggle",
                "help": "Disable progress bar output.",
                "doc_url": f"{DOC_ROOT}#verbosity-and-simulation-options",
            },
            {
                "key": "ignore_errors",
                "label": "ignore-errors",
                "widget": "toggle",
                "help": "Continue playlists after a failed entry (recommended for huge lists).",
                "doc_url": f"{DOC_ROOT}#workarounds",
            },
            {
                "key": "noplaylist",
                "label": "noplaylist",
                "widget": "toggle",
                "help": "Download only the single video when URL is both video and playlist.",
                "doc_url": f"{DOC_ROOT}#video-selection",
            },
            {
                "key": "restrict_filenames",
                "label": "restrict-filenames",
                "widget": "toggle",
                "help": "ASCII-only filenames; strips some punctuation.",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "no_overwrites",
                "label": "no-overwrites (-w)",
                "widget": "toggle",
                "help": "Skip if the target file already exists.",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "continue_dl",
                "label": "continue (-c)",
                "widget": "toggle",
                "help": "Resume partial downloads (enabled by default; turn off to force restart).",
                "doc_url": f"{DOC_ROOT}#filesystem-options",
            },
            {
                "key": "skip_unavailable_fragments",
                "label": "skip-unavailable-fragments",
                "widget": "toggle",
                "help": "Skip missing HLS/DASH fragments instead of aborting.",
                "doc_url": f"{DOC_ROOT}#workarounds",
            },
        ],
    },
]

FORMAT_PRESETS: list[dict[str, str]] = [
    {
        "id": "merge_stack",
        "label": "Merge-first stack",
        "value": (
            "bestvideo*+bestaudio/bestvideo+bestaudio/bestvideo*/best/worst"
        ),
    },
    {
        "id": "compat_pair",
        "label": "Classic bv+ba",
        "value": "bestvideo+bestaudio/best/worst",
    },
    {
        "id": "cap_1080",
        "label": "Cap 1080p",
        "value": (
            "bestvideo[height<=1080]+bestaudio/"
            "bestvideo*[height<=1080]+bestaudio/best/worst"
        ),
    },
    {
        "id": "low_bw",
        "label": "Fast / low bandwidth",
        "value": "best[height<=720]/bestvideo*[height<=720]+bestaudio/best/worst",
    },
    {
        "id": "audio_only",
        "label": "Audio only",
        "value": "bestaudio/best",
    },
]
