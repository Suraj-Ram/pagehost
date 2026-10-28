"""FastMCP entrypoint. `fastmcp run` loads this file and calls `server`."""

from fastmcp import FastMCP

from pagehost.bootstrap import create_server
from pagehost.config import Settings


def server() -> FastMCP:
    return create_server(Settings.from_env())
