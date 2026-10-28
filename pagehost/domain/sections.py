"""Section ids, ranges, and the text a section read returns (§5.2)."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pagehost.domain.errors import SectionNotFound
from pagehost.domain.models import Heading, Section
from pagehost.domain.text import is_blank_line

# Letters and digits, Unicode-aware. Underscore is a separator, not a word character.
_SLUG_TOKEN = re.compile(r"[^\W_]+")
_AVAILABLE_LIMIT = 50


def slug(title: str) -> str:
    """Section id base: lowercase, non-letter/digit runs become ``-``, else ``section``."""
    tokens = _SLUG_TOKEN.findall(title.lower())
    if not tokens:
        return "section"
    return "-".join(tokens)


def build_sections(headings: Sequence[Heading], line_count: int) -> tuple[Section, ...]:
    """One section per heading, in order. Ranges include nested subsections."""
    issued: set[str] = set()
    sections: list[Section] = []
    for index, heading in enumerate(headings):
        section_id = _unique_id(slug(heading.title), issued)
        sections.append(
            Section(
                id=section_id,
                level=heading.level,
                title=heading.title,
                start=heading.line,
                end=_section_end(headings, index, line_count),
            )
        )
    return tuple(sections)


def section_text(lines: Sequence[str], section: Section) -> str:
    """Heading plus body, with leading and trailing blank lines removed."""
    chunk = lines[section.start : section.end]
    start = 0
    end = len(chunk)
    while start < end and is_blank_line(chunk[start]):
        start += 1
    while end > start and is_blank_line(chunk[end - 1]):
        end -= 1
    return "\n".join(chunk[start:end])


def require_section(sections: Sequence[Section], section_id: str) -> Section:
    """Return the section or raise ``section_not_found``."""
    for section in sections:
        if section.id == section_id:
            return section
    available = [section.id for section in sections[:_AVAILABLE_LIMIT]]
    raise SectionNotFound(
        f"Unknown section {section_id!r}.",
        section=section_id,
        available=available,
        total_sections=len(sections),
    )


def deepest_section_id(sections: Sequence[Section], line: int) -> str | None:
    """Id of the deepest section whose range contains 0-based ``line``."""
    found: Section | None = None
    for section in sections:
        if section.start <= line < section.end and (
            found is None
            or section.level > found.level
            or (section.level == found.level and section.start > found.start)
        ):
            found = section
    if found is None:
        return None
    return found.id


def _unique_id(base: str, issued: set[str]) -> str:
    candidate = base
    number = 2
    while candidate in issued:
        candidate = f"{base}-{number}"
        number += 1
    issued.add(candidate)
    return candidate


def _section_end(headings: Sequence[Heading], index: int, line_count: int) -> int:
    heading = headings[index]
    for later in headings[index + 1 :]:
        if later.level <= heading.level:
            return later.line
    return line_count
