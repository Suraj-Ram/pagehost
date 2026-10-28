"""Application service. Every mutation renders, then persists, then publishes (§9.1)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from pagehost.domain.edits import replace_exact
from pagehost.domain.errors import (
    InvalidContent,
    InvalidPageId,
    PageNotFound,
    UnknownFormat,
    UnsupportedOperation,
    VersionConflict,
)
from pagehost.domain.ids import allocate_page_id, is_valid_page_id
from pagehost.domain.models import (
    Document,
    Mutation,
    NewVersion,
    Outline,
    OutlineEntry,
    PageSummary,
    Published,
    SectionView,
    SourceView,
    StoredVersion,
    VersionInfo,
)
from pagehost.domain.normalize import ensure_source_size, normalize_newlines, normalize_title
from pagehost.domain.ports import ContentFormat, PageRepository, SitePublisher, Theme, UrlScheme
from pagehost.domain.sections import build_sections, require_section, section_text
from pagehost.domain.text import changed, is_blank_line, lines_of, splice

_NO_CHANGE = "No change: the result is identical to the current version."
_HEADING_REMOVED = (
    "Replacement does not start with a heading line, so the section's heading was removed. "
    "Include the heading line in `content`."
)


class PagehostService:
    """Use cases behind the MCP tools. Adapters are injected; this module does not import them."""

    def __init__(
        self,
        *,
        pages: PageRepository,
        publisher: SitePublisher,
        urls: UrlScheme,
        theme: Theme,
        formats: Mapping[str, ContentFormat],
        default_format: str,
        max_source_bytes: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._pages = pages
        self._publisher = publisher
        self._urls = urls
        self._theme = theme
        self._formats = dict(formats)
        self._default_format = default_format
        self._max_source_bytes = max_source_bytes
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def publish(
        self,
        title: str,
        content: str,
        *,
        author: str,
        summary: str | None = None,
        format: str | None = None,
    ) -> Published:
        stored_title = normalize_title(title)
        source = normalize_newlines(content)
        ensure_source_size(source, self._max_source_bytes)
        fmt = self._format(self._default_format if format is None else format)
        fragment = fmt.render(source)
        page_id = allocate_page_id(stored_title, self._id_taken)
        stored = self._pages.create(
            page_id,
            self._version(
                title=stored_title,
                format_name=fmt.name,
                source=source,
                author=author,
                summary=summary,
                generated="created",
            ),
        )
        self._publish_stored(stored, fragment.html)
        return Published(
            id=page_id,
            url=self._urls.url_for(page_id),
            version=stored.number,
            warnings=tuple(fragment.warnings),
        )

    def read_source(self, page_id: str, *, version: int | None = None) -> SourceView:
        stored = self._stored(page_id, version)
        return SourceView(version=stored.number, source=stored.source)

    def read_section(
        self, page_id: str, section: str, *, version: int | None = None
    ) -> SectionView:
        stored = self._stored(page_id, version)
        found = require_section(self._require_sections(stored), section)
        text = section_text(lines_of(stored.source), found)
        return SectionView(version=stored.number, section=found.id, source=text)

    def outline(self, page_id: str, *, version: int | None = None) -> Outline:
        stored = self._stored(page_id, version)
        lines = lines_of(stored.source)
        sections = self._sections(stored) or ()
        entries = tuple(
            OutlineEntry(
                id=section.id,
                level=section.level,
                title=section.title,
                tokens=_tokens(section_text(lines, section)),
            )
            for section in sections
        )
        return Outline(version=stored.number, tokens=_tokens(stored.source), sections=entries)

    def append(
        self,
        page_id: str,
        content: str,
        *,
        section: str | None = None,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation:
        current = self._begin(page_id, base_version)
        lines = lines_of(current.source)
        if section is None:
            point = len(lines)
            generated = "append"
        else:
            found = require_section(self._require_sections(current), section)
            point = found.end
            generated = f"append to {section}"
        new_source = "\n".join(splice(lines, point, point, _content_block(content)))
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=new_source,
            author=author,
            summary=summary,
            generated=generated,
        )

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
    ) -> Mutation:
        current = self._begin(page_id, base_version)
        located = self._sections(current)
        if section is not None and located is None:
            raise UnsupportedOperation(f"format {current.format!r} has no sections")
        sections = () if located is None else located
        new_source = replace_exact(
            current.source,
            normalize_newlines(old),
            normalize_newlines(new),
            section_id=section,
            sections=sections,
        )
        generated = "edit text" if section is None else f"edit text in {section}"
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=new_source,
            author=author,
            summary=summary,
            generated=generated,
        )

    def replace_section(
        self,
        page_id: str,
        section: str,
        content: str,
        *,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation:
        current = self._begin(page_id, base_version)
        found = require_section(self._require_sections(current), section)
        block = _content_block(content)
        new_source = "\n".join(splice(lines_of(current.source), found.start, found.end, block))
        extra = (_HEADING_REMOVED,) if self._drops_heading(current, block) else ()
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=new_source,
            author=author,
            summary=summary,
            generated=f"replace section {section}",
            extra_warnings=extra,
        )

    def delete_section(
        self,
        page_id: str,
        section: str,
        *,
        author: str,
        summary: str | None = None,
        base_version: int | None = None,
    ) -> Mutation:
        current = self._begin(page_id, base_version)
        found = require_section(self._require_sections(current), section)
        new_source = "\n".join(splice(lines_of(current.source), found.start, found.end, []))
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=new_source,
            author=author,
            summary=summary,
            generated=f"delete section {section}",
        )

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
    ) -> Mutation:
        current = self._begin(page_id, base_version)
        stored_title = current.title if title is None else normalize_title(title)
        format_name = current.format if format is None else format
        return self._commit(
            current,
            title=stored_title,
            format_name=format_name,
            source=normalize_newlines(content),
            author=author,
            summary=summary,
            generated="full rewrite",
            force=True,
        )

    def list_pages(
        self, *, query: str | None = None, limit: int = 20
    ) -> tuple[int, tuple[PageSummary, ...]]:
        rows = self._pages.list_pages()
        if query:
            needle = query.casefold()
            rows = tuple(
                row
                for row in rows
                if needle in row.title.casefold() or needle in row.page_id.casefold()
            )
        kept = rows[: _at_least_one(limit)]
        entries = tuple(
            PageSummary(
                id=row.page_id,
                title=row.title,
                version=row.number,
                url=self._urls.url_for(row.page_id),
            )
            for row in kept
        )
        return len(rows), entries

    def list_versions(self, page_id: str, *, limit: int | None = None) -> tuple[VersionInfo, ...]:
        self._current(page_id)
        rows = self._pages.list_versions(page_id)
        if limit is not None:
            rows = rows[-_at_least_one(limit) :]
        return tuple(
            VersionInfo(version=row.number, by=row.author, at=row.created_at, summary=row.summary)
            for row in rows
        )

    def rollback(self, page_id: str, to_version: int, *, author: str) -> Mutation:
        current = self._current(page_id)
        target = self._pages.get_version(page_id, to_version)
        return self._commit(
            current,
            title=target.title,
            format_name=target.format,
            source=target.source,
            author=author,
            summary=None,
            generated=f"Rollback to v{to_version}",
            force=True,
        )

    def delete(self, page_id: str) -> None:
        self._current(page_id)
        self._pages.mark_deleted(page_id)
        self._publisher.unpublish(page_id)

    def rerender(self) -> tuple[int, dict[str, str]]:
        self._publisher.install_assets(self._theme.static_assets())
        ok = 0
        failed: dict[str, str] = {}
        for page in self._pages.list_pages():
            try:
                fragment = self._format(page.format).render(page.source)
                self._publish_stored(page, fragment.html)
            except Exception as exc:
                failed[page.page_id] = _failure_message(exc)
            else:
                ok += 1
        return ok, failed

    def _commit(
        self,
        current: StoredVersion,
        *,
        title: str,
        format_name: str,
        source: str,
        author: str,
        summary: str | None,
        generated: str,
        extra_warnings: tuple[str, ...] = (),
        force: bool = False,
    ) -> Mutation:
        ensure_source_size(source, self._max_source_bytes)
        fragment = self._format(format_name).render(source)
        warnings = tuple(fragment.warnings) + extra_warnings
        if source == current.source and not force:
            return Mutation(version=current.number, changed="+0/-0", warnings=warnings + (_NO_CHANGE,))
        stored = self._pages.append_version(
            current.page_id,
            self._version(
                title=title,
                format_name=format_name,
                source=source,
                author=author,
                summary=summary,
                generated=generated,
            ),
            base_version=current.number,
        )
        self._publish_stored(stored, fragment.html)
        return Mutation(version=stored.number, changed=changed(current.source, source), warnings=warnings)

    def _publish_stored(self, stored: StoredVersion, html: str) -> None:
        document = Document(
            page_id=stored.page_id,
            title=stored.title,
            body_html=html,
            version=stored.number,
            updated_at=stored.created_at,
        )
        self._publisher.publish(stored.page_id, stored.number, self._theme.render_document(document))

    def _version(
        self,
        *,
        title: str,
        format_name: str,
        source: str,
        author: str,
        summary: str | None,
        generated: str,
    ) -> NewVersion:
        return NewVersion(
            title=title,
            format=format_name,
            source=source,
            author=author,
            summary=generated if summary is None else summary,
            created_at=self._now(),
        )

    def _begin(self, page_id: str, base_version: int | None) -> StoredVersion:
        current = self._current(page_id)
        if base_version is not None and base_version != current.number:
            raise VersionConflict(
                f"page {page_id} is at version {current.number}",
                expected_version=base_version,
                current_version=current.number,
            )
        return current

    def _current(self, page_id: str) -> StoredVersion:
        self._require_id(page_id)
        return self._pages.get_version(page_id)

    def _stored(self, page_id: str, version: int | None) -> StoredVersion:
        self._require_id(page_id)
        return self._pages.get_version(page_id, version)

    def _format(self, name: str) -> ContentFormat:
        try:
            return self._formats[name]
        except KeyError:
            raise UnknownFormat(f"unknown format {name!r}") from None

    def _sections(self, stored: StoredVersion):
        fmt = self._format(stored.format)
        headings = getattr(fmt, "headings", None)
        if not callable(headings):
            return None
        return build_sections(headings(stored.source), len(lines_of(stored.source)))

    def _require_sections(self, stored: StoredVersion):
        sections = self._sections(stored)
        if sections is None:
            raise UnsupportedOperation(f"format {stored.format!r} has no sections")
        return sections

    def _drops_heading(self, stored: StoredVersion, block: list[str]) -> bool:
        fmt = self._format(stored.format)
        headings = getattr(fmt, "headings", None)
        if not callable(headings):
            return False
        found = headings("\n".join(block))
        return not found or found[0].line != 0

    def _require_id(self, page_id: str) -> None:
        if not is_valid_page_id(page_id):
            raise InvalidPageId(f"invalid page id {page_id!r}")

    def _id_taken(self, page_id: str) -> bool:
        try:
            self._pages.list_versions(page_id)
        except PageNotFound:
            return False
        return True

    def _now(self) -> datetime:
        moment = self._clock()
        if moment.tzinfo is None:
            return moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)


def _content_block(content: str) -> list[str]:
    """Caller content as lines, with surrounding blank lines removed (§5.3)."""
    lines = lines_of(normalize_newlines(content))
    start = 0
    end = len(lines)
    while start < end and is_blank_line(lines[start]):
        start += 1
    while end > start and is_blank_line(lines[end - 1]):
        end -= 1
    block = list(lines[start:end])
    if not block:
        raise InvalidContent("content is empty")
    return block


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def _at_least_one(limit: int) -> int:
    return limit if limit >= 1 else 1


def _failure_message(exc: Exception) -> str:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message:
        return message
    return str(exc)
