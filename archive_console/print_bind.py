"""Print host and port for launcher (reads state.json if present)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
EXAMPLE = HERE / "state.example.json"


def main() -> None:
    data: dict = {}
    if STATE.is_file():
        data = json.loads(STATE.read_text(encoding="utf-8"))
    elif EXAMPLE.is_file():
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    # Always loopback — do not read host from state (prevents accidental LAN bind).
    host = "127.0.0.1"
    port = int(data.get("port", 8756))
    if "--url" in sys.argv:
        print(f"http://{host}:{port}/")
    else:
        print(f"{host} {port}")


if __name__ == "__main__":
    main()
