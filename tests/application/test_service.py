"""PagehostService on in-memory fakes. SPEC §9.1."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from application.fakes import MemoryFormat, MemoryPages, MemoryPublisher, MemoryTheme, MemoryUrls, PlainFormat
from pagehost.application.service import PagehostService
from pagehost.domain.errors import (
    ContentTooLarge,
    EditConflict,
    InvalidContent,
    InvalidPageId,
    PageExists,
    PageNotFound,
    SectionNotFound,
    UnknownFormat,
    UnsupportedOperation,
    VersionConflict,
    VersionNotFound,
)

_NO_CHANGE = "No change: the result is identical to the current version."
_HEADING_REMOVED = (
    "Replacement does not start with a heading line, so the section's heading was removed. "
    "Include the heading line in `content`."
)
_CHANGED = re.compile(r"^\+\d+/-\d+$")


class _Clock:
    def __init__(self) -> None:
        self._n = 0

    def __call__(self) -> datetime:
        self._n += 1
        return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self._n)


def _world(*, max_source_bytes: int = 1_000_000) -> SimpleNamespace:
    trace: list[str] = []
    pages = MemoryPages(trace)
    publisher = MemoryPublisher(trace)
    theme = MemoryTheme(trace)
    fmt = MemoryFormat(trace)
    service = PagehostService(
        pages=pages,
        publisher=publisher,
        urls=MemoryUrls(),
        theme=theme,
        formats={"markdown": fmt, "plain": PlainFormat()},
        default_format="markdown",
        max_source_bytes=max_source_bytes,
        clock=_Clock(),
    )
    return SimpleNamespace(
        service=service, pages=pages, publisher=publisher, fmt=fmt, trace=trace
    )


def test_publish_renders_then_persists_then_publishes():
    world = _world()
    world.fmt.warnings = ("Images are not supported and were removed.",)
    published = world.service.publish("Hello", "body\r\nline", author="ada")

    assert world.trace == ["render", "persist", "theme", "publish"]
    assert published.version == 1
    assert published.id.startswith("hello-")
    assert published.url == f"https://{published.id}.pages.example.com/"
    assert published.warnings == ("Images are not supported and were removed.",)
    stored = world.pages.get_version(published.id)
    assert stored.source == "body\nline"
    assert stored.author == "ada"
    assert stored.summary == "created"
    version, html = world.publisher.served[published.id]
    assert version == 1
    assert html == "v1|Hello|<p>body\nline</p>"


def test_a_failed_render_stores_nothing():
    world = _world()
    world.fmt.fail = True
    with pytest.raises(InvalidContent):
        world.service.publish("Hello", "body", author="ada")
    assert world.pages.creates == 0
    assert world.publisher.served == {}


def test_oversized_source_is_rejected_before_render():
    world = _world(max_source_bytes=4)
    with pytest.raises(ContentTooLarge):
        world.service.publish("Hello", "hello", author="ada")
    assert world.fmt.renders == 0
    assert world.pages.creates == 0


def test_empty_title_is_rejected_before_render():
    world = _world()
    with pytest.raises(InvalidContent):
        world.service.publish("   ", "body", author="ada")
    assert world.fmt.renders == 0


def test_unknown_format_allocates_nothing():
    world = _world()
    with pytest.raises(UnknownFormat):
        world.service.publish("Hello", "body", author="ada", format="rst")
    assert world.pages.creates == 0
    assert world.publisher.served == {}


def test_id_allocation_retries_while_ids_are_taken():
    world = _world()
    world.pages.block_unknown = 4
    published = world.service.publish("Hello", "body", author="ada")
    assert published.id.startswith("hello-")
    assert world.pages.creates == 1
    assert world.pages.block_unknown == 0


def test_id_allocation_gives_up_after_five_taken_ids():
    world = _world()
    world.pages.block_unknown = 5
    with pytest.raises(PageExists):
        world.service.publish("Hello", "body", author="ada")
    assert world.pages.creates == 0
    assert world.publisher.served == {}
    assert world.trace == ["render"]


def test_identical_edit_adds_no_version():
    world = _world()
    published = world.service.publish("Hello", "Hello", author="ada")
    result = world.service.replace_text(published.id, "Hello", "Hello", author="ada")
    assert result.version == 1
    assert result.changed == "+0/-0"
    assert result.warnings[-1] == _NO_CHANGE
    assert len(world.pages.list_versions(published.id)) == 1
    assert world.trace.count("persist") == 1
    assert world.publisher.served[published.id][0] == 1


def test_replace_page_always_creates_a_version():
    world = _world()
    published = world.service.publish("Hello", "same", author="ada")
    result = world.service.replace_page(published.id, "same", author="ada")
    assert result.version == 2
    assert _NO_CHANGE not in result.warnings
    assert world.pages.get_version(published.id).summary == "full rewrite"


def test_rollback_copies_an_earlier_version_forward():
    world = _world()
    published = world.service.publish("Title", "v1", author="ada")
    world.service.replace_page(
        published.id, "v2", title="Renamed", format="plain", author="ada"
    )
    result = world.service.rollback(published.id, 1, author="ada")
    assert result.version == 3
    restored = world.pages.get_version(published.id, 3)
    original = world.pages.get_version(published.id, 1)
    assert restored.source == original.source
    assert restored.title == original.title
    assert restored.format == "markdown"
    assert restored.summary == "Rollback to v1"
    assert world.pages.get_version(published.id, 2).title == "Renamed"
    assert world.pages.get_version(published.id, 2).format == "plain"


def test_missing_rollback_target_stores_nothing():
    world = _world()
    published = world.service.publish("Title", "v1", author="ada")
    with pytest.raises(VersionNotFound):
        world.service.rollback(published.id, 9, author="ada")
    assert len(world.pages.list_versions(published.id)) == 1


def test_failed_publish_is_repaired_by_rerender():
    world = _world()
    world.publisher.fail = True
    with pytest.raises(OSError, match="disk full"):
        world.service.publish("Hello", "body", author="ada")
    stored = world.pages.list_pages()
    assert len(stored) == 1
    assert world.publisher.served == {}

    world.publisher.fail = False
    ok, failed = world.service.rerender()
    assert (ok, failed) == (1, {})
    assert world.publisher.served[stored[0].page_id][0] == 1
    assert world.publisher.assets == {"pagehost.css": b"css"}


def test_rerender_continues_after_one_page_fails():
    world = _world()
    kept = world.service.publish("Alpha", "alpha", author="ada")
    broken = world.service.publish("Beta", "beta", author="ada")
    world.publisher.served.clear()
    world.fmt.bad_source = "beta"
    ok, failed = world.service.rerender()
    assert ok == 1
    assert failed == {broken.id: "cannot compile"}
    assert kept.id in world.publisher.served
    assert broken.id not in world.publisher.served


def test_rerender_installs_assets_when_there_are_no_pages():
    world = _world()
    ok, failed = world.service.rerender()
    assert (ok, failed) == (0, {})
    assert world.publisher.assets == {"pagehost.css": b"css"}


def test_append_inside_a_section_lands_before_the_next_sibling():
    world = _world()
    published = world.service.publish(
        "Plan",
        "## Goals\n\nalpha\n\n## Risks\n\nvendor\n",
        author="ada",
    )
    result = world.service.append(published.id, "- staffing", section="goals", author="ada")
    source = world.service.read_source(published.id).source
    assert result.version == 2
    assert _CHANGED.fullmatch(result.changed)
    assert source.index("- staffing") < source.index("## Risks")
    assert world.pages.get_version(published.id).summary == "append to goals"


def test_replace_text_normalises_newlines_and_keeps_the_supplied_summary():
    world = _world()
    published = world.service.publish("Hello", "a\nb", author="ada")
    result = world.service.replace_text(
        published.id, "a\r\nb", "c", author="ada", summary="ship it"
    )
    assert result.version == 2
    assert world.service.read_source(published.id).source == "c"
    assert world.pages.get_version(published.id).summary == "ship it"


def test_stale_base_version_conflicts_before_a_new_version():
    world = _world()
    published = world.service.publish("Hello", "alpha", author="ada")
    world.service.append(published.id, "beta", author="ada")
    with pytest.raises(VersionConflict) as caught:
        world.service.replace_text(
            published.id, "alpha", "gamma", author="ada", base_version=1
        )
    assert caught.value.details["expected_version"] == 1
    assert caught.value.details["current_version"] == 2
    assert world.pages.get_version(published.id).number == 2


def test_edit_conflict_changes_nothing():
    world = _world()
    published = world.service.publish("Hello", "alpha", author="ada")
    with pytest.raises(EditConflict) as caught:
        world.service.replace_text(published.id, "absent phrase", "x", author="ada")
    assert caught.value.details["matches"] == 0
    assert world.pages.get_version(published.id).number == 1


def test_empty_append_is_invalid_and_stores_nothing():
    world = _world()
    published = world.service.publish("Hello", "alpha", author="ada")
    with pytest.raises(InvalidContent):
        world.service.append(published.id, "\n\n", author="ada")
    assert world.pages.get_version(published.id).number == 1


def test_replace_section_warns_when_the_heading_line_is_missing():
    world = _world()
    warned_page = world.service.publish("Plan", "## Goals\n\nalpha\n", author="ada")
    warned = world.service.replace_section(warned_page.id, "goals", "just prose", author="ada")
    assert _HEADING_REMOVED in warned.warnings

    kept_page = world.service.publish("Other", "## Goals\n\nalpha\n", author="ada")
    kept = world.service.replace_section(kept_page.id, "goals", "## Goals\n\nbeta", author="ada")
    assert _HEADING_REMOVED not in kept.warnings
    section = world.service.read_section(kept_page.id, "goals")
    assert section.source.startswith("## Goals")
    assert "beta" in section.source


def test_unknown_section_is_reported_and_stores_nothing():
    world = _world()
    published = world.service.publish("Plan", "## Goals\n\nalpha\n", author="ada")
    with pytest.raises(SectionNotFound) as caught:
        world.service.delete_section(published.id, "missing", author="ada")
    assert caught.value.details["section"] == "missing"
    assert world.pages.get_version(published.id).number == 1


def test_section_tools_reject_a_format_without_headings():
    world = _world()
    published = world.service.publish("Hello", "alpha", author="ada", format="plain")
    with pytest.raises(UnsupportedOperation):
        world.service.append(published.id, "beta", section="goals", author="ada")
    outline = world.service.outline(published.id)
    assert outline.sections == ()
    assert outline.tokens == math.ceil(len("alpha") / 4)


def test_outline_token_estimates_use_section_text():
    world = _world()
    published = world.service.publish("Plan", "## Goals\n\nalpha\n", author="ada")
    outline = world.service.outline(published.id)
    source = world.service.read_source(published.id).source
    section = world.service.read_section(published.id, "goals").source
    assert outline.sections[0].id == "goals"
    assert outline.tokens == math.ceil(len(source) / 4)
    assert outline.sections[0].tokens == math.ceil(len(section) / 4)


def test_list_pages_filters_before_limit_and_prefers_recent():
    world = _world()
    world.service.publish("Alpha notes", "a", author="ada")
    newer = world.service.publish("Beta", "b", author="ada")
    total, pages = world.service.list_pages(limit=1)
    assert total == 2
    assert [page.id for page in pages] == [newer.id]
    matched, found = world.service.list_pages(query="ALPHA")
    assert matched == 1
    assert found[0].title == "Alpha notes"
    zero, one = world.service.list_pages(limit=0)
    assert zero == 2
    assert len(one) == 1


def test_list_versions_keeps_the_newest_and_returns_oldest_first():
    world = _world()
    published = world.service.publish("Hello", "a", author="ada")
    world.service.append(published.id, "b", author="ada")
    world.service.append(published.id, "c", author="bea")
    versions = world.service.list_versions(published.id, limit=2)
    assert [item.version for item in versions] == [2, 3]
    assert versions[0].summary == "append"
    assert versions[1].by == "bea"


def test_delete_soft_deletes_and_stops_serving():
    world = _world()
    published = world.service.publish("Hello", "body", author="ada")
    world.service.delete(published.id)
    with pytest.raises(PageNotFound):
        world.service.read_source(published.id)
    assert world.service.list_pages() == (0, ())
    assert published.id not in world.publisher.served


def test_invalid_page_id_is_rejected_before_lookup():
    world = _world()
    with pytest.raises(InvalidPageId):
        world.service.read_source("../x")
    assert world.pages.lookups == 0


def test_delete_section_removes_the_section_text():
    world = _world()
    published = world.service.publish(
        "Plan", "## Goals\n\nalpha\n\n## Risks\n\nvendor\n", author="ada"
    )
    result = world.service.delete_section(published.id, "goals", author="ada")
    source = world.service.read_source(published.id).source
    assert result.version == 2
    assert "alpha" not in source
    assert "## Risks" in source
    assert world.pages.get_version(published.id).summary == "delete section goals"
