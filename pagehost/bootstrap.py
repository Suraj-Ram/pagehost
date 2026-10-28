"""Composition root. This is the only module that names concrete adapters."""

from __future__ import annotations

from fastapi import FastAPI

from pagehost.adapters.markdown import MarkdownFormat
from pagehost.adapters.publisher import FilesystemPublisher
from pagehost.adapters.sanitizer import Nh3Sanitizer
from pagehost.adapters.sqlite_repo import SqlitePageRepository
from pagehost.adapters.theme import PagehostTheme
from pagehost.adapters.url_scheme import TemplateUrlScheme
from pagehost.application.service import PagehostService
from pagehost.config import Settings
from pagehost.transports.mcp import build_mcp


def create_app(settings: Settings) -> FastAPI:
    """Wire the real adapters and mount the MCP server at ``/mcp``."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    markdown = MarkdownFormat(Nh3Sanitizer())
    theme = PagehostTheme()
    publisher = FilesystemPublisher(settings.site_root)
    publisher.install_assets(theme.static_assets())
    service = PagehostService(
        pages=SqlitePageRepository(settings.data_dir / "pagehost.sqlite"),
        publisher=publisher,
        urls=TemplateUrlScheme(settings.url_template),
        theme=theme,
        formats={markdown.name: markdown},
        default_format=settings.default_format,
        max_source_bytes=settings.max_source_bytes,
    )
    mcp_app = build_mcp(service, settings).http_app(path="/")
    app = FastAPI(lifespan=mcp_app.lifespan)
    app.mount("/mcp", mcp_app)
    return app
