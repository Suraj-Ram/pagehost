"""In-memory ports for the application service. No disk and no network."""

from __future__ import annotations

from pagehost.domain.errors import (
    InvalidContent,
    PageExists,
    PageNotFound,
    VersionConflict,
    VersionNotFound,
)
from pagehost.domain.models import Document, Heading, NewVersion, RenderedFragment, StoredVersion


class MemoryPages:
    """PageRepository over dictionaries. Deleted ids stay taken."""

    def __init__(self, trace: list[str]) -> None:
        self.trace = trace
        self._versions: dict[str, list[StoredVersion]] = {}
        self._deleted: set[str] = set()
        self.block_unknown = 0
        self.creates = 0
        self.lookups = 0

    def create(self, page_id: str, first: NewVersion) -> StoredVersion:
        if page_id in self._versions:
            raise PageExists(f"page {page_id} already exists")
        self.creates += 1
        self.trace.append("persist")
        stored = _record(page_id, 1, first)
        self._versions[page_id] = [stored]
        return stored

    def append_version(
        self, page_id: str, new: NewVersion, base_version: int | None = None
    ) -> StoredVersion:
        current = self._live(page_id)
        if base_version is not None and base_version != current.number:
            raise VersionConflict(
                f"page {page_id} is at version {current.number}",
                expected_version=base_version,
                current_version=current.number,
            )
        self.trace.append("persist")
        stored = _record(page_id, current.number + 1, new)
        self._versions[page_id].append(stored)
        return stored

    def get_version(self, page_id: str, number: int | None = None) -> StoredVersion:
        self.lookups += 1
        current = self._live(page_id)
        if number is None:
            return current
        for row in self._versions[page_id]:
            if row.number == number:
                return row
        raise VersionNotFound(f"page {page_id} has no version {number}")

    def list_versions(self, page_id: str) -> tuple[StoredVersion, ...]:
        if page_id not in self._versions:
            if self.block_unknown > 0:
                self.block_unknown -= 1
                return ()
            raise PageNotFound(f"page {page_id} not found")
        return tuple(self._versions[page_id])

    def list_pages(self) -> tuple[StoredVersion, ...]:
        live = [
            versions[-1]
            for page_id, versions in self._versions.items()
            if page_id not in self._deleted
        ]
        live.sort(key=lambda row: (-row.created_at.timestamp(), row.page_id))
        return tuple(live)

    def mark_deleted(self, page_id: str) -> None:
        self._live(page_id)
        self._deleted.add(page_id)

    def _live(self, page_id: str) -> StoredVersion:
        if page_id not in self._versions or page_id in self._deleted:
            raise PageNotFound(f"page {page_id} not found")
        return self._versions[page_id][-1]


class MemoryPublisher:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace
        self.served: dict[str, tuple[int, str]] = {}
        self.assets: dict[str, bytes] = {}
        self.fail = False

    def publish(self, page_id: str, version: int, html: str) -> None:
        self.trace.append("publish")
        if self.fail:
            raise OSError("disk full")
        self.served[page_id] = (version, html)

    def unpublish(self, page_id: str) -> None:
        self.served.pop(page_id, None)

    def install_assets(self, assets: dict[str, bytes]) -> None:
        self.assets = dict(assets)


class MemoryTheme:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace

    def render_document(self, document: Document) -> str:
        self.trace.append("theme")
        return f"v{document.version}|{document.title}|{document.body_html}"

    def static_assets(self) -> dict[str, bytes]:
        return {"pagehost.css": b"css"}


class MemoryUrls:
    def url_for(self, page_id: str) -> str:
        return f"https://{page_id}.pages.example.com/"


class MemoryFormat:
    name = "markdown"

    def __init__(self, trace: list[str]) -> None:
        self.trace = trace
        self.warnings: tuple[str, ...] = ()
        self.fail = False
        self.bad_source: str | None = None
        self.renders = 0

    def render(self, source: str) -> RenderedFragment:
        self.renders += 1
        self.trace.append("render")
        if self.fail or source == self.bad_source:
            raise InvalidContent("cannot compile")
        return RenderedFragment(html=f"<p>{source}</p>", warnings=self.warnings)

    def headings(self, source: str) -> tuple[Heading, ...]:
        found: list[Heading] = []
        for index, line in enumerate(source.split("\n")):
            marks = len(line) - len(line.lstrip("#"))
            if not 1 <= marks <= 6 or len(line) == marks or line[marks] != " ":
                continue
            title = line[marks:].strip()
            if title:
                found.append(Heading(level=marks, title=title, line=index))
        return tuple(found)

    def authoring_guide(self) -> str:
        return ""


class PlainFormat:
    """A format with no headings, so section operations are unsupported."""

    name = "plain"

    def render(self, source: str) -> RenderedFragment:
        return RenderedFragment(html=source, warnings=())

    def authoring_guide(self) -> str:
        return ""


def _record(page_id: str, number: int, new: NewVersion) -> StoredVersion:
    return StoredVersion(
        page_id=page_id,
        number=number,
        title=new.title,
        format=new.format,
        source=new.source,
        author=new.author,
        summary=new.summary,
        created_at=new.created_at,
        size_bytes=len(new.source.encode("utf-8")),
    )
