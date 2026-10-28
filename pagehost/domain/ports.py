"""Ports the application service depends on. Adapters implement these; they do not import each other."""

from __future__ import annotations

from typing import Protocol

from pagehost.domain.models import Document, Heading, NewVersion, RenderedFragment, StoredVersion


class ContentFormat(Protocol):
    name: str

    def render(self, source: str) -> RenderedFragment:
        """Pure and deterministic. Returns a sanitized fragment."""

    def authoring_guide(self) -> str:
        """Short guide charged on every MCP connection."""


class SectionedFormat(Protocol):
    def headings(self, source: str) -> tuple[Heading, ...]:
        """Top-level headings in document order. `line` is a 0-based index."""


class HtmlSanitizer(Protocol):
    def clean(self, html: str) -> str:
        """Allowlist-based clean. Used by content formats."""


class Theme(Protocol):
    def render_document(self, document: Document) -> str:
        """Wrap a fragment in the page shell."""

    def static_assets(self) -> dict[str, bytes]:
        """Files the document links, keyed by asset name."""


class PageRepository(Protocol):
    def create(self, page_id: str, first: NewVersion) -> StoredVersion:
        """Store version 1. `page_exists` if the id is taken, including soft-deleted ids."""

    def append_version(
        self, page_id: str, new: NewVersion, base_version: int | None = None
    ) -> StoredVersion:
        """Add version current+1. Stale `base_version` raises `version_conflict`."""

    def get_version(self, page_id: str, number: int | None = None) -> StoredVersion:
        """`number` omitted means the current version."""

    def list_versions(self, page_id: str) -> tuple[StoredVersion, ...]:
        """Every version, oldest first. Source may be omitted by the caller; records include it."""

    def list_pages(self) -> tuple[StoredVersion, ...]:
        """Current version of each live page, most recently updated first."""

    def mark_deleted(self, page_id: str) -> None:
        """Soft delete. `page_not_found` if absent or already deleted."""


class SitePublisher(Protocol):
    def publish(self, page_id: str, version: int, html: str) -> None:
        """Idempotent. A reader sees the old page or the new page."""

    def unpublish(self, page_id: str) -> None:
        """Remove the current pointer only. History stays on disk."""

    def install_assets(self, assets: dict[str, bytes]) -> None:
        """Install shared files such as the stylesheet."""


class UrlScheme(Protocol):
    def url_for(self, page_id: str) -> str:
        """Substitute `{id}` in the configured template."""
