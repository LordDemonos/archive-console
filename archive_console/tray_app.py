"""
Tray helper for Archive Console (Windows-first). Starts the same process line as CLI:

  python -m uvicorn app.main:app --host 127.0.0.1 --port <port>

Run from ``archive_console`` with venv active: ``pythonw tray_app.py`` (no console) or
``python tray_app.py`` when debugging.

Process layout (Windows-first):

- **Spawn mode:** this file is the **parent** process (tray). It ``Popen``s a **child**
  ``python -m uvicorn app.main:app`` (see ``spawn()``). Stopping the HTTP server
  (Settings ``POST /api/shutdown`` → ``os._exit`` on the child) ends **only** the child
  unless the tray also exits — a **watchdog** calls ``icon.stop()`` when ``proc.poll()``
  is non-``None`` so the tray icon does not orphan.
- **Attach mode:** health check saw an existing listener; ``proc`` stays ``None``. The
  tray is just a menu + notify listener; **Exit** does not stop uvicorn (use Settings or
  kill the server process). **Settings → Stop** stops the server; the tray icon remains
  until **Exit** in the menu.

See ARCHIVE_CONSOLE.md (``app.server_cli.uvicorn_argv``; attach vs spawn).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

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


def _tray_notify_bind_port() -> int:
    """Match app.settings.effective_tray_notify_port without importing the app package early."""
    data: dict = {}
    if STATE.is_file():
        data = json.loads(STATE.read_text(encoding="utf-8"))
    elif EXAMPLE.is_file():
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    raw = int(data.get("tray_notify_port", 0) or 0)
    if raw > 0:
        return raw
    main_p = int(data.get("port", 8756))
    cand = main_p + 101
    return cand if cand <= 65535 else 8860


def _start_notify_http(notify_port: int, icon_holder: dict) -> None:
    """POST /notify {title, body} on 127.0.0.1 only → pystray balloon."""

    class NotifyHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            ip = self.client_address[0]
            if ip not in ("127.0.0.1", "::1"):
                self.send_error(403)
                return
            parsed = urlparse(self.path)
            if parsed.path.rstrip("/") != "/notify":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > 8192:
                self.send_error(400)
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.send_error(400)
                return
            title = str(payload.get("title") or "Archive Console").strip() or "Archive Console"
            body = str(payload.get("body") or "").strip()
            if not body:
                self.send_error(400)
                return
            icon = icon_holder.get("icon")
            if icon is None:
                self.send_error(503)
                return
            try:
                icon.notify(body, title)
            except Exception as e:
                log.warning("Tray notify failed: %s", e)
                self.send_error(500)
                return
            self.send_response(204)
            self.end_headers()

    def serve() -> None:
        try:
            server = HTTPServer(("127.0.0.1", notify_port), NotifyHandler)
        except OSError as e:
            log.warning(
                "Tray notify HTTP server not started on 127.0.0.1:%s (%s). "
                "Change tray_notify_port in state if needed.",
                notify_port,
                e,
            )
            return
        log.info("Tray notify listener on http://127.0.0.1:%s/notify", notify_port)
        server.serve_forever()

    threading.Thread(target=serve, name="archive_console_tray_notify", daemon=True).start()


def _server_python_executable() -> str:
    """Use python.exe for the uvicorn child when the tray runs as pythonw (no console)."""
    p = Path(sys.executable)
    if p.name.lower() == "pythonw.exe":
        cand = p.with_name("python.exe")
        if cand.is_file():
            return str(cand)
    return sys.executable


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


def _try_shutdown_server_http(host: str, port: int) -> bool:
    """Ask the running server to exit via POST /api/shutdown (same primitive as Settings UI)."""
    try:
        import urllib.error
        import urllib.request

        payload = json.dumps({"confirm": "SHUTDOWN"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://{host}:{port}/api/shutdown",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        tok = (os.environ.get("ARCHIVE_SHUTDOWN_TOKEN") or "").strip()
        if tok:
            req.add_header("X-Archive-Shutdown-Token", tok)
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            return int(resp.status) == 200
    except Exception as e:
        log.debug("Tray: HTTP shutdown failed (%s); falling back to terminate.", e)
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
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0,
                    "Install tray deps (from archive_console folder):\n"
                    "  .venv\\Scripts\\python.exe -m pip install -r requirements.txt",
                    "Archive Console tray",
                    0x10,
                )
            except Exception:
                print("Install tray deps: pip install pystray Pillow", file=sys.stderr)
        else:
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
        argv = [_server_python_executable(), "-m", *uvicorn_argv(host=host, port=port)]
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

    _tray_stopping = False
    _tray_stop_lock = threading.Lock()

    def stop_tray_once() -> None:
        """End ``icon.run()``; safe if ``pystray`` is already stopping."""
        nonlocal _tray_stopping
        with _tray_stop_lock:
            if _tray_stopping:
                return
            _tray_stopping = True
        try:
            icon.stop()
        except Exception:
            pass

    def on_quit(_icon, _item) -> None:
        nonlocal attached
        if attached:
            log.info("Tray exit (attached mode - server left running)")
            stop_tray_once()
            return
        if _run_in_progress(host, port) and not _confirm_force_quit():
            return
        if _try_shutdown_server_http(host, port):
            with lock:
                if proc is not None and proc.poll() is None:
                    try:
                        proc.wait(timeout=14)
                    except subprocess.TimeoutExpired:
                        log.warning(
                            "Tray: server did not exit after HTTP shutdown; terminating pid %s",
                            proc.pid,
                        )
                        stop_server()
                proc = None
        else:
            stop_server()
        stop_tray_once()

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
    notify_port = _tray_notify_bind_port()
    _start_notify_http(notify_port, {"icon": icon})

    if not attached:
        def watch_uvicorn_child() -> None:
            while True:
                time.sleep(0.45)
                with lock:
                    p = proc
                if p is None:
                    continue
                if p.poll() is None:
                    continue
                log.info(
                    "Tray-spawned server exited (pid %s, return code %s); exiting tray.",
                    p.pid,
                    p.returncode,
                )
                stop_tray_once()
                return

        threading.Thread(
            target=watch_uvicorn_child,
            name="archive_console_tray_child_watch",
            daemon=True,
        ).start()

    try:
        icon.run()
    finally:
        if not attached:
            stop_server()


if __name__ == "__main__":
    main()
