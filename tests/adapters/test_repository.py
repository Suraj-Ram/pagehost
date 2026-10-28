import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pagehost.adapters.sqlite_repo import SqlitePageRepository
from pagehost.domain.errors import PageExists, PageNotFound, VersionConflict, VersionNotFound
from pagehost.domain.models import NewVersion, StoredVersion


def _new(
    *,
    title: str = "Weekly notes",
    format: str = "markdown",
    source: str = "hello",
    author: str = "agent",
    summary: str | None = "created",
    created_at: datetime | None = None,
) -> NewVersion:
    return NewVersion(
        title=title,
        format=format,
        source=source,
        author=author,
        summary=summary,
        created_at=created_at or datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc),
    )


def _stored(page_id: str, number: int, new: NewVersion, *, deleted: bool = False) -> StoredVersion:
    created_at = new.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    return StoredVersion(
        page_id=page_id,
        number=number,
        title=new.title,
        format=new.format,
        source=new.source,
        author=new.author,
        summary=new.summary,
        created_at=created_at,
        size_bytes=len(new.source.encode("utf-8")),
        deleted=deleted,
    )


def test_create_stores_version_one(tmp_path: Path):
    path = tmp_path / "pages.sqlite"
    repo = SqlitePageRepository(path)
    first = _new(source="héllo")

    stored = repo.create("page-a", first)

    assert stored == _stored("page-a", 1, first)
    assert stored.size_bytes == len("héllo".encode("utf-8"))
    assert SqlitePageRepository(path).get_version("page-a") == stored
    assert repo.get_version("page-a", None) == stored


def test_create_rejects_an_existing_id_including_one_soft_deleted(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    repo.create("page-a", _new())

    with pytest.raises(PageExists) as duplicate:
        repo.create("page-a", _new(source="other"))
    assert duplicate.value.code == "page_exists"
    assert repo.get_version("page-a").source == "hello"

    repo.mark_deleted("page-a")
    with pytest.raises(PageExists):
        repo.create("page-a", _new(source="revived"))
    assert repo.create("page-b", _new()).number == 1


def test_append_version_adds_one_past_current(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    first = _new(source="v1", created_at=datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc))
    second = _new(
        source="v2",
        summary=None,
        created_at=datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc),
    )
    third = _new(source="v3", created_at=datetime(2026, 10, 27, 17, 0, tzinfo=timezone.utc))
    repo.create("page-a", first)

    stored = repo.append_version("page-a", second, base_version=1)
    omitted = repo.append_version("page-a", third)

    assert stored == _stored("page-a", 2, second)
    assert omitted == _stored("page-a", 3, third)
    assert repo.get_version("page-a") == omitted
    assert repo.get_version("page-a", 1) == _stored("page-a", 1, first)


def test_stale_base_version_conflicts_and_writes_nothing(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    repo.create("page-a", _new(source="v1"))
    repo.append_version("page-a", _new(source="v2"))
    before = repo.list_versions("page-a")

    with pytest.raises(VersionConflict) as conflict:
        repo.append_version("page-a", _new(source="stale"), base_version=1)

    assert conflict.value.code == "version_conflict"
    assert conflict.value.details == {"expected_version": 1, "current_version": 2}
    assert repo.list_versions("page-a") == before
    assert repo.get_version("page-a").source == "v2"


def test_missing_page_raises_page_not_found(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")

    with pytest.raises(PageNotFound) as missing_get:
        repo.get_version("missing-id")
    with pytest.raises(PageNotFound):
        repo.get_version("missing-id", 1)
    with pytest.raises(PageNotFound):
        repo.append_version("missing-id", _new(), base_version=1)
    with pytest.raises(PageNotFound):
        repo.list_versions("missing-id")
    with pytest.raises(PageNotFound):
        repo.mark_deleted("missing-id")

    assert missing_get.value.code == "page_not_found"
    assert repo.list_pages() == ()


def test_missing_version_raises_version_not_found(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    repo.create("page-a", _new())

    with pytest.raises(VersionNotFound) as missing:
        repo.get_version("page-a", 2)

    assert missing.value.code == "version_not_found"
    assert repo.get_version("page-a").number == 1


def test_list_versions_are_oldest_first_and_include_source(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    first = _new(source="one", created_at=datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc))
    second = _new(source="two", created_at=datetime(2026, 10, 27, 15, 5, tzinfo=timezone.utc))
    third = _new(source="three", created_at=datetime(2026, 10, 27, 15, 9, tzinfo=timezone.utc))
    repo.create("page-a", first)
    repo.append_version("page-a", third)
    repo.append_version("page-a", second)

    listed = repo.list_versions("page-a")

    assert listed == (
        _stored("page-a", 1, first),
        _stored("page-a", 2, third),
        _stored("page-a", 3, second),
    )
    assert [version.source for version in listed] == ["one", "three", "two"]


def test_list_pages_is_newest_current_version_first_then_id(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    same = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    earlier = datetime(2026, 10, 27, 11, 0, tzinfo=timezone.utc)
    later = datetime(2026, 10, 27, 13, 0, tzinfo=timezone.utc)
    repo.create("page-c", _new(source="old-c", created_at=earlier))
    repo.create("page-b", _new(source="b", created_at=same))
    repo.create("page-a", _new(source="a", created_at=same))
    repo.append_version("page-c", _new(source="new-c", created_at=later))

    listed = repo.list_pages()

    assert [(page.page_id, page.number, page.source) for page in listed] == [
        ("page-c", 2, "new-c"),
        ("page-a", 1, "a"),
        ("page-b", 1, "b"),
    ]


def test_soft_delete_keeps_history_and_hides_current_reads(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    first = _new(source="v1")
    second = _new(source="v2", created_at=datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc))
    repo.create("page-a", first)
    repo.append_version("page-a", second)
    repo.create("page-b", _new(source="live"))

    repo.mark_deleted("page-a")

    with pytest.raises(PageNotFound) as hidden:
        repo.get_version("page-a")
    with pytest.raises(PageNotFound):
        repo.get_version("page-a", 1)
    with pytest.raises(PageNotFound):
        repo.append_version("page-a", _new(source="nope"))
    with pytest.raises(PageNotFound):
        repo.mark_deleted("page-a")

    assert hidden.value.code == "page_not_found"
    assert repo.list_versions("page-a") == (
        _stored("page-a", 1, first, deleted=True),
        _stored("page-a", 2, second, deleted=True),
    )
    assert [page.page_id for page in repo.list_pages()] == ["page-b"]


def test_timestamps_are_utc(tmp_path: Path):
    repo = SqlitePageRepository(tmp_path / "pages.sqlite")
    eastern = timezone(timedelta(hours=-4))
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=eastern)

    stored = repo.create("page-a", _new(created_at=created_at))

    assert stored.created_at == datetime(2026, 1, 2, 7, 4, 5, tzinfo=timezone.utc)
    assert repo.get_version("page-a").created_at == stored.created_at


def test_writes_use_wal_mode(tmp_path: Path):
    path = tmp_path / "pages.sqlite"
    SqlitePageRepository(path)

    with sqlite3.connect(path) as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_concurrent_appends_of_the_same_base_do_not_both_land(tmp_path: Path):
    path = tmp_path / "pages.sqlite"
    SqlitePageRepository(path).create("page-a", _new(source="v1"))
    barrier = threading.Barrier(2)
    results: list[StoredVersion | VersionConflict] = []
    lock = threading.Lock()

    def attempt(source: str) -> None:
        repo = SqlitePageRepository(path)
        barrier.wait(timeout=5)
        try:
            outcome: StoredVersion | VersionConflict = repo.append_version(
                "page-a",
                _new(source=source),
                base_version=1,
            )
        except VersionConflict as error:
            outcome = error
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt, args=(source,)) for source in ("left", "right")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert [thread.is_alive() for thread in threads] == [False, False]
    saved = [item for item in results if isinstance(item, StoredVersion)]
    conflicts = [item for item in results if isinstance(item, VersionConflict)]
    assert [version.number for version in saved] == [2]
    assert len(conflicts) == 1
    assert conflicts[0].details == {"expected_version": 1, "current_version": 2}
    versions = SqlitePageRepository(path).list_versions("page-a")
    assert [version.number for version in versions] == [1, 2]
    assert versions[1].source == saved[0].source
