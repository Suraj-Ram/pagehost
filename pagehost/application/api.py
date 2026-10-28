"""Use-case surface frozen for the MCP transport and the service implementation.

The MCP transport decides when a read is an outline. This protocol exposes the primitives.
"""

from __future__ import annotations

from typing import Protocol

from pagehost.domain.models import (
    Mutation,
    Outline,
    PageSummary,
    Published,
    SectionView,
    SourceView,
    VersionInfo,
)


class PageService(Protocol):
    def publish(
        self,
        title: str,
        content: str,
        *,
        author: str,
        summary: str | None = None,
        format: str | None = None,
    ) -> Published: ...

    def read_source(self, page_id: str, *, version: int | None = None) -> SourceView: ...

    def read_section(self, page_id: str, section: str, *, version: int | None = None) -> SectionView: ...

    def outline(self, page_id: str, *, version: int | None = None) -> Outline: ...

    def append(
        self,
        page_id: str,
        content: str,
        *,
        section: str | None = None,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation: ...

    def replace_text(
        self,
        page_id: str,
        old: str,
        new: str,
        *,
        section: str | None = None,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation: ...

    def replace_section(
        self,
        page_id: str,
        section: str,
        content: str,
        *,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation: ...

    def delete_section(
        self,
        page_id: str,
        section: str,
        *,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation: ...

    def replace_page(
        self,
        page_id: str,
        content: str,
        *,
        title: str | None = None,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
        format: str | None = None,
    ) -> Mutation: ...

    def list_pages(self, *, query: str | None = None, limit: int = 20) -> tuple[int, tuple[PageSummary, ...]]:
        """Return `(total_before_limit, page_entries)`."""

    def list_versions(self, page_id: str, *, limit: int | None = None) -> tuple[VersionInfo, ...]:
        """Oldest first. `limit` keeps the most recent N."""

    def rollback(self, page_id: str, to_version: int, *, author: str) -> Mutation: ...

    def delete(self, page_id: str) -> None: ...

    def rerender(self) -> tuple[int, dict[str, str]]:
        """Return `(ok_count, failed_id_to_message)`."""
