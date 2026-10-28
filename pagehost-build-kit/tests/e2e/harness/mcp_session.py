"""MCP transport adapter: the only place the harness knows it is talking MCP."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from .runner import ToolFailure


class McpSession:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        try:
            return (await self._client.call_tool(tool, args)).data
        except ToolError as e:
            raise _failure(str(e)) from None

    async def tool_names(self) -> set[str]:
        return {t.name for t in await self._client.list_tools()}


def _failure(text: str) -> ToolFailure:
    """Tool errors are a JSON object: {code, message, details?}."""
    try:
        body = json.loads(text[text.index("{"):])
        return ToolFailure(body["code"], body.get("message", ""), body.get("details"))
    except (ValueError, KeyError):
        return ToolFailure("unparseable_error", text)


@asynccontextmanager
async def connect(url: str, token: str):
    transport = StreamableHttpTransport(url, headers={"Authorization": f"Bearer {token}"})
    async with Client(transport) as client:
        yield McpSession(client)
