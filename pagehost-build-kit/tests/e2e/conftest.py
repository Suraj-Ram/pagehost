"""Where the system under test is chosen. This is the ONLY implementation-aware file in e2e/.

Default: boot the real server (HTTP, bearer auth, MCP) on a free port, in a thread.
Remote:  set PAGEHOST_E2E_MCP_URL (+ PAGEHOST_E2E_TOKEN, optionally PAGEHOST_E2E_PAGE_ORIGIN)
         to run the very same scenarios against any deployment or re-implementation.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest

from e2e.harness.http_fetch import HttpFetcher
from e2e.harness.mcp_session import connect
from e2e.harness.runner import PageNotServed

TOKEN = "e2e-token"


class Endpoint:
    def __init__(self, mcp_url: str, token: str, fetch) -> None:
        self.mcp_url, self.token, self.fetch = mcp_url, token, fetch

    def connect(self):
        return connect(self.mcp_url, self.token)


class DirectoryFetcher:
    """Stands in for the web server in front of the pages (nginx in production): maps a page
    URL to the published file. Needed only because the local run has no web server."""

    def __init__(self, site_root: Path) -> None:
        self._root = site_root

    def __call__(self, url: str) -> str:
        page_id = (urlparse(url).hostname or "").split(".")[0]
        path = self._root / page_id / "current" / "index.html"
        if not page_id or not path.is_file():
            raise PageNotServed(url)
        return path.read_text()


@pytest.fixture(scope="session")
def endpoint(tmp_path_factory):
    remote = os.environ.get("PAGEHOST_E2E_MCP_URL")
    if remote:
        yield Endpoint(remote, os.environ["PAGEHOST_E2E_TOKEN"],
                       HttpFetcher(os.environ.get("PAGEHOST_E2E_PAGE_ORIGIN")))
        return

    import uvicorn

    from pagehost.bootstrap import create_server
    from pagehost.config import Settings

    settings = Settings(data_dir=tmp_path_factory.mktemp("e2e"), token=TOKEN,
                        url_template="http://{id}.pages.e2e.test/")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_server(settings).http_app(), host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    try:
        yield Endpoint(f"http://127.0.0.1:{port}/mcp/", TOKEN, DirectoryFetcher(settings.site_root))
    finally:
        server.should_exit = True
        thread.join(timeout=10)
