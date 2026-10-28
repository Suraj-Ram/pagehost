"""SQLite adapter for the page repository port."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pagehost.domain.errors import PageExists, PageNotFound, VersionConflict, VersionNotFound
from pagehost.domain.models import NewVersion, StoredVersion

_T = TypeVar("_T")

_PAGE_COLUMNS = """
    v.page_id, v.number, v.title, v.format, v.source, v.author,
    v.summary, v.created_at, v.size_bytes, p.deleted
"""

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS pages (
        id TEXT PRIMARY KEY,
        deleted INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS versions (
        page_id TEXT NOT NULL REFERENCES pages(id),
        number INTEGER NOT NULL,
        title TEXT NOT NULL,
        format TEXT NOT NULL,
        source TEXT NOT NULL,
        author TEXT NOT NULL,
        summary TEXT,
        created_at TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        PRIMARY KEY (page_id, number)
    )
    """,
)


class SqlitePageRepository:
    def __init__(self, path: Path) -> None:
        # MCP runs tools on a worker thread. One lock keeps the shared connection serial.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(Path(path), isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._immediate(self._create_schema)

    def create(self, page_id: str, first: NewVersion) -> StoredVersion:
        def write() -> StoredVersion:
            if self._page_row(page_id) is not None:
                raise PageExists(f"page {page_id} already exists")
            self._conn.execute(
                "INSERT INTO pages (id, deleted) VALUES (?, 0)",
                (page_id,),
            )
            return self._insert_version(page_id, 1, first)

        return self._immediate(write)

    def append_version(
        self, page_id: str, new: NewVersion, base_version: int | None = None
    ) -> StoredVersion:
        def write() -> StoredVersion:
            page = self._page_row(page_id)
            if page is None or page["deleted"]:
                raise PageNotFound(f"page {page_id} not found")
            current = self._current_number(page_id)
            if base_version is not None and base_version != current:
                raise VersionConflict(
                    f"page {page_id} is at version {current}",
                    expected_version=base_version,
                    current_version=current,
                )
            return self._insert_version(page_id, current + 1, new)

        return self._immediate(write)

    def get_version(self, page_id: str, number: int | None = None) -> StoredVersion:
        with self._lock:
            return self._get_version(page_id, number)

    def _get_version(self, page_id: str, number: int | None = None) -> StoredVersion:
        row = self._conn.execute(
            f"""
            SELECT {_PAGE_COLUMNS}
            FROM pages AS p
            LEFT JOIN versions AS v
              ON v.page_id = p.id
             AND v.number = COALESCE(
                    ?,
                    (SELECT MAX(number) FROM versions WHERE page_id = p.id)
                 )
            WHERE p.id = ?
            """,
            (number, page_id),
        ).fetchone()
        if row is None or row["deleted"]:
            raise PageNotFound(f"page {page_id} not found")
        if row["number"] is None:
            label = "current" if number is None else str(number)
            raise VersionNotFound(f"page {page_id} has no version {label}")
        return _stored(row)

    def list_versions(self, page_id: str) -> tuple[StoredVersion, ...]:
        with self._lock:
            return self._list_versions(page_id)

    def _list_versions(self, page_id: str) -> tuple[StoredVersion, ...]:
        if self._page_row(page_id) is None:
            raise PageNotFound(f"page {page_id} not found")
        rows = self._conn.execute(
            f"""
            SELECT {_PAGE_COLUMNS}
            FROM versions AS v
            JOIN pages AS p ON p.id = v.page_id
            WHERE v.page_id = ?
            ORDER BY v.number ASC
            """,
            (page_id,),
        ).fetchall()
        return tuple(_stored(row) for row in rows)

    def list_pages(self) -> tuple[StoredVersion, ...]:
        with self._lock:
            return self._list_pages()

    def _list_pages(self) -> tuple[StoredVersion, ...]:
        rows = self._conn.execute(
            f"""
            SELECT {_PAGE_COLUMNS}
            FROM pages AS p
            JOIN versions AS v ON v.page_id = p.id
            WHERE p.deleted = 0
              AND v.number = (SELECT MAX(number) FROM versions WHERE page_id = p.id)
            ORDER BY v.created_at DESC, p.id ASC
            """
        ).fetchall()
        return tuple(_stored(row) for row in rows)

    def mark_deleted(self, page_id: str) -> None:
        def write() -> None:
            page = self._page_row(page_id)
            if page is None or page["deleted"]:
                raise PageNotFound(f"page {page_id} not found")
            self._conn.execute("UPDATE pages SET deleted = 1 WHERE id = ?", (page_id,))

        self._immediate(write)

    def _create_schema(self) -> None:
        for statement in _SCHEMA:
            self._conn.execute(statement)

    def _immediate(self, write: Callable[[], _T]) -> _T:
        with self._lock:
            return self._immediate_locked(write)

    def _immediate_locked(self, write: Callable[[], _T]) -> _T:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            result = write()
            self._conn.execute("COMMIT")
        except Exception:
            self._rollback()
            raise
        return result

    def _rollback(self) -> None:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    def _page_row(self, page_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT id, deleted FROM pages WHERE id = ?",
            (page_id,),
        ).fetchone()

    def _current_number(self, page_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(number) AS number FROM versions WHERE page_id = ?",
            (page_id,),
        ).fetchone()
        if row is None or row["number"] is None:
            raise PageNotFound(f"page {page_id} not found")
        return int(row["number"])

    def _insert_version(self, page_id: str, number: int, new: NewVersion) -> StoredVersion:
        created_at = _as_utc(new.created_at)
        size_bytes = len(new.source.encode("utf-8"))
        self._conn.execute(
            """
            INSERT INTO versions (
                page_id, number, title, format, source, author, summary, created_at, size_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                number,
                new.title,
                new.format,
                new.source,
                new.author,
                new.summary,
                _format_timestamp(created_at),
                size_bytes,
            ),
        )
        return StoredVersion(
            page_id=page_id,
            number=number,
            title=new.title,
            format=new.format,
            source=new.source,
            author=new.author,
            summary=new.summary,
            created_at=created_at,
            size_bytes=size_bytes,
            deleted=False,
        )


def _stored(row: sqlite3.Row) -> StoredVersion:
    return StoredVersion(
        page_id=row["page_id"],
        number=int(row["number"]),
        title=row["title"],
        format=row["format"],
        source=row["source"],
        author=row["author"],
        summary=row["summary"],
        created_at=_parse_timestamp(row["created_at"]),
        size_bytes=int(row["size_bytes"]),
        deleted=bool(row["deleted"]),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return _as_utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
