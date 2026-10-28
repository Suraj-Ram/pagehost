"""Domain records shared by the service and the transports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    title: str
    line: int


@dataclass(frozen=True, slots=True)
class Section:
    id: str
    level: int
    title: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Candidate:
    """One `edit_conflict` hint. `line` is 1-based and absolute in the page."""

    line: int
    snippet: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class RenderedFragment:
    html: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NewVersion:
    title: str
    format: str
    source: str
    author: str
    summary: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StoredVersion:
    page_id: str
    number: int
    title: str
    format: str
    source: str
    author: str
    summary: str | None
    created_at: datetime
    size_bytes: int
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class Document:
    page_id: str
    title: str
    body_html: str
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Published:
    id: str
    url: str
    version: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Mutation:
    version: int
    changed: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceView:
    version: int
    source: str


@dataclass(frozen=True, slots=True)
class SectionView:
    version: int
    section: str
    source: str


@dataclass(frozen=True, slots=True)
class OutlineEntry:
    id: str
    level: int
    title: str
    tokens: int


@dataclass(frozen=True, slots=True)
class Outline:
    version: int
    tokens: int
    sections: tuple[OutlineEntry, ...]


@dataclass(frozen=True, slots=True)
class PageSummary:
    id: str
    title: str
    version: int
    url: str


@dataclass(frozen=True, slots=True)
class VersionInfo:
    version: int
    by: str
    at: datetime
    summary: str | None = None
