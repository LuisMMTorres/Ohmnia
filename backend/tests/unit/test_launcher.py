"""The browser must be able to reach the server after slow application startup."""

import asyncio
import urllib.request

import pytest
import uvicorn

from circuitos.__main__ import BrowserServer


@pytest.mark.parametrize("open_browser", [True, False])
def test_browser_waits_for_ready_server(monkeypatch, open_browser):
    async def scenario():
        initializing = asyncio.Event()
        ready = asyncio.Event()
        opened = []

        async def app(scope, receive, send):
            if scope["type"] == "lifespan":
                await receive()
                initializing.set()
                await ready.wait()
                await send({"type": "lifespan.startup.complete"})
                await receive()
                await send({"type": "lifespan.shutdown.complete"})
            else:
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ready"})

        server = BrowserServer(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"),
            "http://127.0.0.1/" if open_browser else None,
        )

        def browser_open(_url):
            port = server.servers[0].sockets[0].getsockname()[1]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                opened.append(response.read())
            return True

        monkeypatch.setattr("circuitos.__main__.webbrowser.open", browser_open)
        task = asyncio.create_task(server.serve())
        try:
            await asyncio.wait_for(initializing.wait(), timeout=5)
            await asyncio.sleep(0.05)
            assert not server.started
            assert opened == []
            ready.set()
            async with asyncio.timeout(5):
                while not server.started or (open_browser and not opened):
                    await asyncio.sleep(0.01)
            assert opened == ([b"ready"] if open_browser else [])
        finally:
            ready.set()
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())
