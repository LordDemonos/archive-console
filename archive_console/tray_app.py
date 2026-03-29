"""
Tray helper for Archive Console (Windows-first). Starts the same process line as CLI:

  python -m uvicorn app.main:app --host 127.0.0.1 --port <port>

Run from ``archive_console`` with venv active: ``python tray_app.py``
See ARCHIVE_CONSOLE.md (single codepath: ``app.server_cli.uvicorn_argv``; attach vs spawn).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
EXAMPLE = HERE / "state.example.json"
TRAY_ICO_NAME = "tray.ico"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("archive_console.tray")

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _assets_dir() -> Path:
    """Directory containing tray.ico (dev: archive_console/assets; frozen: MEIPASS/assets)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return HERE / "assets"


def _win32_try_per_monitor_dpi_aware() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # 2 = PROCESS_PER_MONITOR_DPI_V2 / per-monitor aware (best effort)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _load_tray_image_from_ico(path: Path):
    from PIL import Image

    im = Image.open(path)
    best = im.convert("RGBA")
    best_area = best.size[0] * best.size[1]
    n = getattr(im, "n_frames", 1)
    for i in range(1, n):
        try:
            im.seek(i)
        except (EOFError, OSError):
            break
        area = im.size[0] * im.size[1]
        if area > best_area:
            best = im.convert("RGBA")
            best_area = area
    return best


def load_tray_image():
    """Tray raster: packaged tray.ico if present, else Pillow fallback (logged)."""
    ico_path = _assets_dir() / TRAY_ICO_NAME
    if ico_path.is_file():
        try:
            return _load_tray_image_from_ico(ico_path)
        except Exception as e:
            log.error("Tray: failed to load %s (%s); using generated icon.", ico_path, e)
    else:
        log.warning(
            "Tray: icon missing at %s (dev: commit assets/%s; "
            "PyInstaller: --add-data \"assets/%s;assets\") — using generated icon.",
            ico_path,
            TRAY_ICO_NAME,
            TRAY_ICO_NAME,
        )

    from tray_icon_raster import draw_tray_icon

    return draw_tray_icon(64)


def _bind() -> tuple[str, int]:
    data: dict = {}
    if STATE.is_file():
        data = json.loads(STATE.read_text(encoding="utf-8"))
    elif EXAMPLE.is_file():
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return "127.0.0.1", int(data.get("port", 8756))


def _archive_root() -> Path:
    data: dict = {}
    if STATE.is_file():
        data = json.loads(STATE.read_text(encoding="utf-8"))
    elif EXAMPLE.is_file():
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw = (data.get("archive_root") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return HERE.parent.resolve()


def _health_ok(host: str, port: int) -> bool:
    try:
        import urllib.error
        import urllib.request

        urllib.request.urlopen(
            f"http://{host}:{port}/api/health",
            timeout=2.0,
        )
        return True
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _run_in_progress(host: str, port: int) -> bool:
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(f"http://{host}:{port}/api/run/status")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            j = json.loads(resp.read().decode())
        return j.get("phase") == "running"
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def _confirm_force_quit() -> bool:
    if sys.platform == "win32":
        import ctypes

        MB_YESNO = 0x04
        IDYES = 6
        r = ctypes.windll.user32.MessageBoxW(
            0,
            "A download job appears to be running. Exit anyway? "
            "The batch subprocess may keep running until it finishes.",
            "Archive Console",
            MB_YESNO | 0x30,
        )
        return r == IDYES
    return True


def main() -> None:
    _win32_try_per_monitor_dpi_aware()
    try:
        import pystray  # noqa: F401
    except ImportError as e:
        print("Install tray deps: pip install pystray Pillow", file=sys.stderr)
        raise SystemExit(1) from e

    import pystray

    from app.server_cli import uvicorn_argv

    host, port = _bind()
    url = f"http://{host}:{port}/"
    root = _archive_root()
    logs = root / "logs"

    proc: subprocess.Popen | None = None
    lock = threading.Lock()
    attached = _health_ok(host, port)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def spawn() -> subprocess.Popen:
        argv = [sys.executable, "-m", *uvicorn_argv(host=host, port=port)]
        log.info("Starting server: %s", " ".join(argv[2:]))
        return subprocess.Popen(
            argv,
            cwd=str(HERE),
            creationflags=creationflags,
        )

    def ensure_server(icon: pystray.Icon | None, _item=None) -> None:
        nonlocal proc, attached
        if attached:
            return
        with lock:
            if proc is not None and proc.poll() is None:
                return
            proc = spawn()

    def stop_server() -> None:
        nonlocal proc
        with lock:
            if proc is not None and proc.poll() is None:
                log.info("Stopping tray-spawned server (pid %s)", proc.pid)
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                            capture_output=True,
                            creationflags=creationflags,
                        )
                    else:
                        proc.kill()
            proc = None

    def open_ui(_icon, _item) -> None:
        webbrowser.open(url)

    def open_logs(_icon, _item) -> None:
        path = str(logs if logs.is_dir() else root)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])

    def restart(_icon, _item) -> None:
        nonlocal attached
        if attached:
            log.warning("Restart ignored: attached to an existing server (not started by this tray).")
            return
        stop_server()
        ensure_server(None)

    def on_quit(icon, _item) -> None:
        nonlocal attached
        if attached:
            log.info("Tray exit (attached mode - server left running)")
            icon.stop()
            return
        if _run_in_progress(host, port) and not _confirm_force_quit():
            return
        stop_server()
        icon.stop()

    if attached:
        log.info(
            "Attached to existing server at %s (port %s). Exit closes the tray only.",
            host,
            port,
        )
    else:
        ensure_server(None)
        log.info("Tray spawned server on %s:%s", host, port)

    menu = pystray.Menu(
        pystray.MenuItem("Open web console", open_ui, default=True),
        pystray.MenuItem("Open logs folder", open_logs),
        pystray.MenuItem("Restart server", restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_quit),
    )
    image = load_tray_image()
    tip = (
        f"Archive Console - attached :{port} (server already running)"
        if attached
        else f"Archive Console - http://{host}:{port}/"
    )
    icon = pystray.Icon(
        "archive_console",
        image,
        tip,
        menu,
    )
    try:
        icon.run()
    finally:
        if not attached:
            stop_server()


if __name__ == "__main__":
    main()
