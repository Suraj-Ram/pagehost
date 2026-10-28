"""Exact-match replacement and near-miss candidates (§5.5)."""

from __future__ import annotations

from collections.abc import Sequence
from difflib import SequenceMatcher

from pagehost.domain.errors import EditConflict, InvalidContent
from pagehost.domain.models import Candidate, Section
from pagehost.domain.sections import deepest_section_id, require_section
from pagehost.domain.text import is_blank_line, lines_of

_MAX_CANDIDATES = 3
_SCAN_LINE_LIMIT = 5000
_PROBE_CHARS = 120
_COMPARE_CHARS = 400
_SNIPPET_CHARS = 100
_MIN_PROBE_CHARS = 3


def replace_exact(
    source: str,
    old: str,
    new: str,
    *,
    section_id: str | None,
    sections: Sequence[Section],
) -> str:
    """Replace the single literal occurrence of ``old`` with ``new``.

    When ``section_id`` is set, only that section's line range is searched.
    ``old`` empty raises ``invalid_content``. Zero or several matches raise
    ``edit_conflict`` and the source is left unchanged (all-or-nothing).
    Conflict details carry ``matches`` and at most three ``candidates``.
    ``current_source`` and ``edit_index`` are omitted.
    """
    if old == "":
        raise InvalidContent("old must not be empty.")

    if section_id is None:
        start_line = 0
        end_line = len(lines_of(source))
    else:
        section = require_section(sections, section_id)
        start_line = section.start
        end_line = section.end

    offsets = _line_offsets(source)
    char_start = _char_at_line(offsets, start_line, len(source))
    char_end = _char_at_line(offsets, end_line, len(source))
    positions = [
        char_start + index for index in _find_all(source[char_start:char_end], old)
    ]
    if len(positions) == 1:
        start = positions[0]
        return source[:start] + new + source[start + len(old) :]

    lines = lines_of(source)
    if len(positions) > 1:
        candidates = [
            _candidate(lines, _line_index(offsets, position), sections)
            for position in positions[:_MAX_CANDIDATES]
        ]
        raise EditConflict(
            f"old matched {len(positions)} times.",
            matches=len(positions),
            candidates=candidates,
        )

    candidates = _near_misses(lines, start_line, end_line, old, sections)
    raise EditConflict(
        "old was not found.",
        matches=0,
        candidates=candidates,
    )


def _find_all(haystack: str, needle: str) -> list[int]:
    found: list[int] = []
    start = 0
    step = len(needle)
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return found
        found.append(index)
        start = index + step


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    cursor = 0
    while True:
        newline = source.find("\n", cursor)
        if newline < 0:
            return offsets
        cursor = newline + 1
        offsets.append(cursor)


def _char_at_line(offsets: Sequence[int], line: int, source_len: int) -> int:
    if line >= len(offsets):
        return source_len
    if line < 0:
        return 0
    return offsets[line]


def _line_index(offsets: Sequence[int], position: int) -> int:
    low = 0
    high = len(offsets) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if offsets[mid] <= position:
            low = mid
        else:
            high = mid - 1
    return low


def _candidate(lines: Sequence[str], line: int, sections: Sequence[Section]) -> Candidate:
    return Candidate(
        line=line + 1,
        snippet=lines[line].strip()[:_SNIPPET_CHARS],
        section=deepest_section_id(sections, line),
    )


def _probe(old: str) -> str | None:
    for line in old.split("\n"):
        if is_blank_line(line):
            continue
        probe = line.strip()[:_PROBE_CHARS]
        if len(probe) < _MIN_PROBE_CHARS:
            return None
        return probe
    return None


def _near_misses(
    lines: Sequence[str],
    start_line: int,
    end_line: int,
    old: str,
    sections: Sequence[Section],
) -> list[Candidate]:
    probe = _probe(old)
    if probe is None:
        return []
    matcher = SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(probe)
    minimum = (len(probe) * 4 + 4) // 5
    ranked: list[tuple[float, int]] = []
    seen: set[str] = set()
    stop = min(end_line, start_line + _SCAN_LINE_LIMIT)
    for index in range(start_line, stop):
        trimmed = lines[index].strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        compared = trimmed[:_COMPARE_CHARS]
        if len(compared) < minimum:
            continue
        matcher.set_seq1(compared)
        matched = sum(size for _i, _j, size in matcher.get_matching_blocks())
        if matched * 5 < len(probe) * 4:
            continue
        ranked.append((matched / len(probe), index))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [_candidate(lines, index, sections) for _score, index in ranked[:_MAX_CANDIDATES]]
