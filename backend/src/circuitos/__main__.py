"""``python -m circuitos``: start the local server and open the browser."""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Sistema de projeto de circuitos")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not args.no_browser:
        url = f"http://{args.host}:{args.port}/"
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    from circuitos.api.app import app  # an object, not a string: works inside the installer

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
