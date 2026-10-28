"""Appendix C vectors for splice, sections, and exact-match edits."""

from __future__ import annotations

import time

import pytest

from pagehost.domain.edits import replace_exact
from pagehost.domain.errors import EditConflict, InvalidContent, SectionNotFound
from pagehost.domain.models import Candidate, Heading, Section
from pagehost.domain.sections import build_sections, require_section, section_text, slug
from pagehost.domain.text import changed, line_delta, lines_of, splice

_LINES = ["## A", "", "a", "", "## B", "", "b", ""]

_PLAN = "## Plan\n\nShip beta on Nov 1\n\n## Risks\n\nVendor ships Nov 1 too\nStaffing gap\n"


def _plan_sections() -> tuple[Section, ...]:
    lines = lines_of(_PLAN)
    headings = (Heading(2, "Plan", 0), Heading(2, "Risks", 4))
    return build_sections(headings, len(lines))


@pytest.mark.parametrize(
    ("lines", "start", "end", "block", "expected"),
    [
        (_LINES, 0, 4, ["## A", "", "new"], "## A\n\nnew\n\n## B\n\nb\n"),
        (_LINES, 4, 8, ["## B", "", "new"], "## A\n\na\n\n## B\n\nnew\n"),
        (_LINES, 8, 8, ["## C"], "## A\n\na\n\n## B\n\nb\n\n## C\n"),
        (_LINES, 4, 4, ["## X"], "## A\n\na\n\n## X\n\n## B\n\nb\n"),
        (_LINES, 0, 4, [], "## B\n\nb\n"),
        (_LINES, 4, 8, [], "## A\n\na\n"),
        (["## A", ""], 0, 2, [], ""),
        ([""], 1, 1, ["hello"], "hello\n"),
    ],
)
def test_splice_matches_appendix_c(lines, start, end, block, expected):
    result = splice(lines, start, end, block)
    assert "\n".join(result) == expected
    assert result[-1] == ""


def test_lines_of_keeps_the_trailing_empty_line():
    assert lines_of("## A\n\na\n\n## B\n\nb\n") == _LINES
    assert lines_of("") == [""]


@pytest.mark.parametrize(
    ("old", "new", "added", "removed"),
    [
        ("a\nb\nc", "a\nX\nY\nc", 2, 1),
        ("same", "same", 0, 0),
        ("", "x\ny\n", 2, 0),
        ("a\nb\n", "a\n", 0, 1),
    ],
)
def test_line_delta_matches_appendix_c(old, new, added, removed):
    assert line_delta(old, new) == (added, removed)
    assert changed(old, new) == f"+{added}/-{removed}"


def test_line_delta_ignores_trailing_newlines_only():
    assert line_delta("a\nb\n", "a\nb") == (0, 0)
    assert line_delta("a\n\n", "a\n") == (0, 0)


def test_section_ranges_include_subsections():
    headings = (
        Heading(2, "A", 0),
        Heading(3, "A1", 3),
        Heading(3, "A2", 6),
        Heading(2, "B", 9),
    )
    assert build_sections(headings, 12) == (
        Section("a", 2, "A", 0, 9),
        Section("a1", 3, "A1", 3, 6),
        Section("a2", 3, "A2", 6, 9),
        Section("b", 2, "B", 9, 12),
    )
    deep = build_sections((Heading(3, "Deep", 0), Heading(2, "Shallow", 4)), 8)
    assert deep == (
        Section("deep", 3, "Deep", 0, 4),
        Section("shallow", 2, "Shallow", 4, 8),
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Q4 Roadmap & Risks!", "q4-roadmap-risks"),
        ("***", "section"),
        ("Überblick", "überblick"),
        ("Risks_2", "risks-2"),
    ],
)
def test_slug_rules(title, expected):
    assert slug(title) == expected


def test_duplicate_slugs_recheck_issued_ids():
    titles = ["Risks", "Risks", "Risks 2", "Risks"]
    headings = tuple(Heading(2, title, index) for index, title in enumerate(titles))
    assert [section.id for section in build_sections(headings, 4)] == [
        "risks",
        "risks-2",
        "risks-2-2",
        "risks-3",
    ]


def test_section_text_drops_edge_blanks_and_keeps_the_heading():
    lines = lines_of(_PLAN)
    sections = _plan_sections()
    assert section_text(lines, sections[0]) == "## Plan\n\nShip beta on Nov 1"
    assert section_text(lines, sections[1]) == "## Risks\n\nVendor ships Nov 1 too\nStaffing gap"
    padded = ["", "  ", "## A", "body", "", "tail"]
    assert section_text(padded, Section("a", 2, "A", 0, 6)) == "## A\nbody\n\ntail"


def test_unknown_section_lists_at_most_fifty_ids():
    headings = tuple(Heading(2, f"Part {index}", index) for index in range(60))
    sections = build_sections(headings, 60)
    with pytest.raises(SectionNotFound) as caught:
        require_section(sections, "missing")
    details = caught.value.details
    assert details["section"] == "missing"
    assert details["total_sections"] == 60
    assert details["available"] == [section.id for section in sections[:50]]
    assert "part-50" not in details["available"]
    assert set(details) == {"section", "available", "total_sections"}


def test_replace_exact_conflict_for_two_occurrences():
    sections = _plan_sections()
    with pytest.raises(EditConflict) as caught:
        replace_exact(_PLAN, "Nov 1", "Dec 1", section_id=None, sections=sections)
    error = caught.value
    assert error.code == "edit_conflict"
    assert error.details["matches"] == 2
    assert error.details["candidates"] == [
        Candidate(3, "Ship beta on Nov 1", "plan"),
        Candidate(7, "Vendor ships Nov 1 too", "risks"),
    ]
    assert "current_source" not in error.details
    assert "edit_index" not in error.details


def test_near_miss_for_double_space():
    with pytest.raises(EditConflict) as caught:
        replace_exact(_PLAN, "Staffing  gap", "x", section_id=None, sections=_plan_sections())
    assert caught.value.details["matches"] == 0
    assert caught.value.details["candidates"] == [Candidate(8, "Staffing gap", "risks")]


def test_scoped_near_miss_keeps_absolute_line_numbers():
    with pytest.raises(EditConflict) as caught:
        replace_exact(
            _PLAN,
            "Staffing gapp",
            "x",
            section_id="risks",
            sections=_plan_sections(),
        )
    assert caught.value.details["matches"] == 0
    assert caught.value.details["candidates"] == [Candidate(8, "Staffing gap", "risks")]


def test_scoped_miss_cannot_see_outside_the_section():
    with pytest.raises(EditConflict) as caught:
        replace_exact(_PLAN, "Staffing gap", "x", section_id="plan", sections=_plan_sections())
    assert caught.value.details["matches"] == 0
    assert caught.value.details.get("candidates", []) == []


def test_unrelated_text_has_no_candidates():
    with pytest.raises(EditConflict) as caught:
        replace_exact(
            _PLAN,
            "quarterly revenue forecast",
            "x",
            section_id=None,
            sections=_plan_sections(),
        )
    assert caught.value.details == {"matches": 0}


def test_empty_old_is_invalid_content():
    with pytest.raises(InvalidContent) as caught:
        replace_exact(_PLAN, "", "x", section_id=None, sections=_plan_sections())
    assert caught.value.code == "invalid_content"


def test_unknown_section_on_edit():
    with pytest.raises(SectionNotFound) as caught:
        replace_exact(_PLAN, "Staffing gap", "x", section_id="nope", sections=_plan_sections())
    assert caught.value.details["section"] == "nope"
    assert caught.value.details["total_sections"] == 2


def test_unique_match_replaces_once_inside_the_section():
    sections = _plan_sections()
    updated = replace_exact(_PLAN, "Nov 1", "Dec 1", section_id="plan", sections=sections)
    assert updated == _PLAN.replace("Ship beta on Nov 1", "Ship beta on Dec 1")
    assert "Vendor ships Nov 1 too" in updated
    deleted = replace_exact(_PLAN, "Staffing gap", "", section_id="risks", sections=sections)
    assert deleted == _PLAN.replace("Staffing gap", "")


def test_non_overlapping_matches_only():
    assert replace_exact("aaa\n", "aa", "b", section_id=None, sections=()) == "ba\n"


def test_more_than_three_matches_keep_the_first_three_lines():
    source = "\n".join(["one", "two", "one", "one", "one", "three"]) + "\n"
    with pytest.raises(EditConflict) as caught:
        replace_exact(source, "one", "1", section_id=None, sections=())
    assert caught.value.details["matches"] == 4
    assert [item.line for item in caught.value.details["candidates"]] == [1, 3, 4]


def test_snippet_is_the_trimmed_line_capped_at_100_chars():
    body = ("token " * 40).strip()
    source = f"{body}\n{body}\n"
    with pytest.raises(EditConflict) as caught:
        replace_exact(source, "token", "x", section_id=None, sections=())
    snippet = caught.value.details["candidates"][0].snippet
    assert snippet == body[:100]
    assert len(snippet) == 100


def test_duplicate_match_reports_the_deepest_section():
    lines = [
        "## Parent",
        "",
        "shared",
        "### Child",
        "",
        "shared",
        "## Next",
        "",
    ]
    source = "\n".join(lines) + "\n"
    headings = (Heading(2, "Parent", 0), Heading(3, "Child", 3), Heading(2, "Next", 6))
    sections = build_sections(headings, len(lines_of(source)))
    with pytest.raises(EditConflict) as caught:
        replace_exact(source, "shared", "x", section_id=None, sections=sections)
    assert caught.value.details["candidates"] == [
        Candidate(3, "shared", "parent"),
        Candidate(6, "shared", "child"),
    ]


def test_near_miss_orders_by_score_then_line_and_skips_duplicates():
    lines = ["plain filler that should not resemble the probe at all"] * 9
    lines[0] = "abcdefghij"
    lines[2] = "abcdefghijZ"
    lines[4] = "abcdefghijZ"
    lines[5] = "abcdefghijY"
    lines[8] = "abcdefghijX"
    source = "\n".join(lines) + "\n"
    with pytest.raises(EditConflict) as caught:
        replace_exact(source, "abcdefghijZZ", "x", section_id=None, sections=())
    # Z (line 3) outscores the 10/12 ties. Those ties sort by line: 1, then 6.
    # Line 5 repeats line 3's trimmed text, so it is not scored. Line 9 is the fourth.
    assert [item.line for item in caught.value.details["candidates"]] == [3, 1, 6]


def test_probe_shorter_than_three_characters_has_no_candidates():
    with pytest.raises(EditConflict) as caught:
        replace_exact("abcdef\n", "zz", "q", section_id=None, sections=())
    assert caught.value.details == {"matches": 0}


def test_near_miss_scans_at_most_5000_lines():
    lines = [f"row {index:04d} plain background text" for index in range(5001)]
    lines[4999] = "abcdefghijZ"
    lines[5000] = "abcdefghijY"
    source = "\n".join(lines) + "\n"
    with pytest.raises(EditConflict) as caught:
        replace_exact(source, "abcdefghijZZ", "x", section_id=None, sections=())
    assert [item.line for item in caught.value.details["candidates"]] == [5000]

    lines = [f"row {index:04d} plain background text" for index in range(5001)]
    lines[5000] = "abcdefghijZ"
    source = "\n".join(lines) + "\n"
    with pytest.raises(EditConflict) as caught:
        replace_exact(source, "abcdefghijZZ", "x", section_id=None, sections=())
    assert caught.value.details == {"matches": 0}


def test_near_miss_on_a_4000_line_page_is_fast():
    lines = [f"note {index:04d} talks about weather, lunch, and commuting" for index in range(4000)]
    lines[3210] = "Ship the quarterly report before Friday"
    source = "\n".join(lines) + "\n"
    started = time.perf_counter()
    with pytest.raises(EditConflict) as caught:
        replace_exact(
            source,
            "Ship the quarterly report before Fridai",
            "updated",
            section_id=None,
            sections=(),
        )
    elapsed = time.perf_counter() - started
    assert elapsed < 2
    assert caught.value.details["matches"] == 0
    assert caught.value.details["candidates"] == [
        Candidate(3211, "Ship the quarterly report before Friday", None)
    ]
