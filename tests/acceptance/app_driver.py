"""Drive one scenario through the real publish path and read the served page."""

from __future__ import annotations

from pathlib import Path

from acceptance.operations import (
    Append,
    DeletePage,
    DeleteSection,
    Operation,
    Publish,
    ReplacePage,
    ReplaceSection,
    ReplaceText,
    Rollback,
)
from acceptance.runner import Driver
from pagehost.adapters.markdown import MarkdownFormat
from pagehost.adapters.publisher import FilesystemPublisher
from pagehost.adapters.sanitizer import Nh3Sanitizer
from pagehost.adapters.sqlite_repo import SqlitePageRepository
from pagehost.adapters.theme import PagehostTheme
from pagehost.adapters.url_scheme import TemplateUrlScheme
from pagehost.application.service import PagehostService
from pagehost.config import Settings


class AppDriver:
    """One page on a real service. `fragment` is the published document."""

    def __init__(self, data_dir: Path) -> None:
        settings = Settings(
            data_dir=data_dir,
            token="test-token",
            url_template="http://{id}.pages.test/",
        )
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        theme = PagehostTheme()
        publisher = FilesystemPublisher(settings.site_root)
        publisher.install_assets(theme.static_assets())
        markdown = MarkdownFormat(Nh3Sanitizer())
        self._service = PagehostService(
            pages=SqlitePageRepository(settings.data_dir / "pagehost.sqlite"),
            publisher=publisher,
            urls=TemplateUrlScheme(settings.url_template),
            theme=theme,
            formats={markdown.name: markdown},
            default_format=settings.default_format,
            max_source_bytes=settings.max_source_bytes,
        )
        self._site_root = settings.site_root
        self._author = settings.mcp_author
        self._page_id: str | None = None

    def apply(self, operation: Operation) -> None:
        author = self._author
        if isinstance(operation, Publish):
            published = self._service.publish(operation.title, operation.content, author=author)
            self._page_id = published.id
            return
        page_id = self._require_page()
        if isinstance(operation, Append):
            self._service.append(page_id, operation.content, section=operation.section, author=author)
        elif isinstance(operation, ReplaceText):
            self._service.replace_text(
                page_id, operation.old, operation.new, section=operation.section, author=author
            )
        elif isinstance(operation, ReplaceSection):
            self._service.replace_section(
                page_id, operation.section, operation.content, author=author
            )
        elif isinstance(operation, DeleteSection):
            self._service.delete_section(page_id, operation.section, author=author)
        elif isinstance(operation, ReplacePage):
            self._service.replace_page(
                page_id, operation.content, title=operation.title, author=author
            )
        elif isinstance(operation, Rollback):
            self._service.rollback(page_id, operation.to_version, author=author)
        elif isinstance(operation, DeletePage):
            self._service.delete(page_id)
        else:
            raise TypeError(f"unsupported operation {type(operation).__name__}")

    def fragment(self) -> str:
        path = self._site_root / self._require_page() / "current" / "index.html"
        return path.read_text(encoding="utf-8")

    def _require_page(self) -> str:
        if self._page_id is None:
            raise RuntimeError("publish a page before editing it")
        return self._page_id


def open_app(data_dir: Path) -> Driver:
    return AppDriver(data_dir)
