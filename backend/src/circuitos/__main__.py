"""``python -m circuitos``: start the local server and open the browser."""

from __future__ import annotations

import argparse
import asyncio
import socket
import webbrowser

import uvicorn


class BrowserServer(uvicorn.Server):
    """Open the UI only after application startup and socket binding succeed."""

    def __init__(self, config: uvicorn.Config, browser_url: str | None) -> None:
        super().__init__(config)
        self.browser_url = browser_url

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started and not self.should_exit and self.browser_url:
            await asyncio.to_thread(webbrowser.open, self.browser_url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ohmnia: projeto e simulação de circuitos")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    from circuitos.api.app import app  # an object, not a string: works inside the installer

    browser_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    browser_host = "[::1]" if browser_host == "::" else browser_host
    url = None if args.no_browser else f"http://{browser_host}:{args.port}/"
    BrowserServer(uvicorn.Config(app, host=args.host, port=args.port), url).run()


if __name__ == "__main__":
    main()
