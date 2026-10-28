"""The composition root serves MCP and writes an inert page."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from pathlib import Path

import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from starlette.routing import Mount

from pagehost.bootstrap import create_app
from pagehost.config import Settings

_HOSTILE = "<script>alert(1)</script>\n\n# Stolen\n\nplain text"


def test_create_app_installs_assets_and_mounts_mcp(tmp_path: Path):
    settings = _settings(tmp_path)
    app = create_app(settings)

    css = settings.site_root / "_assets" / "pagehost.css"
    expected = Path(__file__).resolve().parents[1] / "pagehost" / "assets" / "pagehost.css"
    assert css.is_file()
    assert css.read_bytes() == expected.read_bytes()
    assert any(isinstance(route, Mount) and route.path == "/mcp" for route in app.routes)


def test_publish_writes_inert_html_without_an_author_h1(tmp_path: Path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    server, thread, port = _serve(app)
    try:
        published = asyncio.run(_publish(port))
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    html = (settings.site_root / published["id"] / "current" / "index.html").read_text()
    lowered = html.lower()
    assert lowered.count("<h1") == 1
    assert "<script" not in lowered
    assert "&lt;script&gt;" in html
    assert "plain text" in html
    assert "Hello" in html


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        token="test-token",
        url_template="http://{id}.pages.test/",
    )


def _serve(app) -> tuple[uvicorn.Server, threading.Thread, int]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    return server, thread, port


async def _publish(port: int) -> dict:
    url = f"http://127.0.0.1:{port}/mcp/"
    async with Client(StreamableHttpTransport(url)) as client:
        result = await client.call_tool(
            "publish_page",
            {"title": "Hello", "content": _HOSTILE},
        )
    data = result.data
    assert isinstance(data, dict)
    return data
