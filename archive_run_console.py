"""
Optional console styling for monthly archive Python drivers.

Strategy: enable Windows virtual-terminal sequences when possible; emit SGR colors
only when stdout is a TTY and NO_COLOR / ARCHIVE_PLAIN_LOG are unset.

run.log and other files always receive plain text (callers strip or avoid SGR in log_line).

Disable styling: NO_COLOR=1, ARCHIVE_PLAIN_LOG=1, or redirect stdout (not a TTY).

Pip noise: set ARCHIVE_PIP_VERBOSE=1 in the environment before the monthly .bat to
restore full pip output (otherwise pip uses -q in the batch recipes).
"""

from __future__ import annotations

import os
import sys

_WIN_VT_DONE = False

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[91m"
GREEN = "\x1b[92m"
YELLOW = "\x1b[93m"
CYAN = "\x1b[96m"

# role -> prefix SGR (no RESET)
_ROLE_PREFIX = {
    "header": f"{BOLD}{CYAN}",
    "ok": f"{BOLD}{GREEN}",
    "warn": f"{BOLD}{YELLOW}",
    "error": f"{BOLD}{RED}",
    "info": CYAN,
    "dim": DIM,
    "skip": f"{DIM}{YELLOW}",
}


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("ARCHIVE_PLAIN_LOG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    try:
        return sys.stdout.isatty()
    except (ValueError, AttributeError):
        return False


def enable_windows_vt() -> None:
    """Best-effort ENABLE_VIRTUAL_TERMINAL_PROCESSING for stdout/stderr (Windows 10+)."""
    global _WIN_VT_DONE
    if _WIN_VT_DONE or sys.platform != "win32":
        return
    try:
        import ctypes

        k = ctypes.windll.kernel32
        ENABLE_VT = 0x0004
        for std_id in (-11, -12):
            h = k.GetStdHandle(std_id)
            if not h or h == ctypes.c_void_p(-1).value:
                continue
            mode = ctypes.c_uint32()
            if not k.GetConsoleMode(h, ctypes.byref(mode)):
                continue
            k.SetConsoleMode(h, mode.value | ENABLE_VT)
    except Exception:
        pass
    _WIN_VT_DONE = True


def init_console() -> None:
    """Call once per process before colored output (drivers invoke at start of main)."""
    enable_windows_vt()


def wrap(role: str, text: str) -> str:
    if not color_enabled():
        return text
    pre = _ROLE_PREFIX.get(role)
    if not pre:
        return text
    return f"{pre}{text}{RESET}"


def print_role(line: str, role: str = "info", *, file=sys.stdout) -> None:
    print(wrap(role, line), file=file)


def classify_ytdlp_line(plain: str) -> str | None:
    """Map a stripped yt-dlp screen line to a role, or None to leave message unchanged."""
    if not (plain or "").strip():
        return None
    low = plain.lower()
    if plain.startswith("error") or plain.startswith("ERROR"):
        return "error"
    if ": error:" in low:
        return "error"
    if plain.startswith("warning") or plain.startswith("WARNING"):
        return "warn"
    if plain.startswith("[download]") and "has already been recorded in the archive" in low:
        return "skip"
    if plain.startswith("[download]") and "finished downloading playlist" in low:
        return "ok"
    if plain.startswith("[debug]"):
        return "dim"
    return None


def augment_ytdlp_console_message(original: str, plain: str) -> str:
    """
    If plain text classifies for emphasis and the original has no SGR, return colored plain.
    Otherwise keep yt-dlp's original (preserves native progress / spinner ANSI).
    """
    if not color_enabled() or not plain:
        return original
    if "\x1b[" in original:
        return original
    role = classify_ytdlp_line(plain)
    if not role:
        return original
    pre = _ROLE_PREFIX.get(role)
    if not pre:
        return original
    return f"{pre}{plain}{RESET}"


def append_plain_run_log(log_dir: str, lines: list[str]) -> None:
    try:
        p = os.path.join(log_dir, "run.log")
        with open(p, "a", encoding="utf-8") as lf:
            for ln in lines:
                lf.write(ln + "\n")
    except OSError:
        pass


def emit_final_summary(
    *,
    log_dir: str,
    log_stamp: str,
    report_path: str,
    rc: int,
    driver_label: str,
    pointer_lines: list[str] | None = None,
) -> None:
    """Bold colored outcome + paths on the console; plain lines appended to run.log."""
    pointer_lines = pointer_lines or []
    bar = "=" * 72
    if rc == 0:
        status = f"[archive] {driver_label}: SUCCESS (exit {rc})"
        detail = "All scheduled steps finished; see summary.txt / report.html for counts."
    else:
        status = f"[archive] {driver_label}: FINISHED WITH ERRORS (exit {rc})"
        detail = "Review issues.csv and run.log; partial work may still be under output folders."
    plain_lines = [
        bar,
        status,
        detail,
        f"Run id: {log_stamp}",
        f"Log directory: {log_dir}",
        f"Report: {report_path}",
        *pointer_lines,
        bar,
    ]
    append_plain_run_log(log_dir, plain_lines)

    init_console()
    role = "ok" if rc == 0 else "error"
    print_role(status, role)
    print_role(detail, "dim")
    print_role(f"Run id: {log_stamp}", "info")
    print_role(f"Log directory: {log_dir}", "dim")
    print_role(f"Report: {report_path}", "info")
    for pl in pointer_lines:
        print_role(pl, "dim")
    print_role(bar, "dim")


def emit_driver_start_banner(
    reporter,
    *,
    title: str,
    subtitle: str = "",
) -> None:
    """Stage header: logged plain + colored on TTY."""
    bar = "=" * 72
    reporter.log_line(bar)
    reporter.log_line(title)
    if subtitle:
        reporter.log_line(subtitle)
    reporter.log_line(bar)
    if not color_enabled():
        return
    init_console()
    print_role(bar, "header")
    print_role(title, "header")
    if subtitle:
        print_role(subtitle, "dim")
    print_role(bar, "header")
