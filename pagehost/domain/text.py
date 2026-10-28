"""Line splitting, splicing, and change summaries (§5.1, §5.3, §5.6)."""

from __future__ import annotations

from collections.abc import Sequence


def lines_of(source: str) -> list[str]:
    """Split source on ``\\n``. A trailing newline yields a final empty line."""
    return source.split("\n")


def is_blank_line(line: str) -> bool:
    """A blank line is empty or whitespace-only."""
    return line.strip() == ""


def splice(lines: Sequence[str], start: int, end: int, block: Sequence[str]) -> list[str]:
    """Replace ``lines[start:end]`` with ``block`` and normalise the seams (§5.3).

    The returned list always ends with ``""``, so ``"\\n".join(result)`` ends with a
    single newline except when every part was empty (that join is ``""``).
    """
    head = _without_trailing_blanks(lines[:start])
    tail = _without_edge_blanks(lines[end:])
    out: list[str] = head
    for part in (block, tail):
        if not part:
            continue
        if out:
            out.append("")
        out.extend(part)
    out.append("")
    return out


def line_delta(old: str, new: str) -> tuple[int, int]:
    """Return ``(added, removed)`` line counts for the changed region (§5.6)."""
    old_lines = _delta_lines(old)
    new_lines = _delta_lines(new)
    prefix = 0
    limit = min(len(old_lines), len(new_lines))
    while prefix < limit and old_lines[prefix] == new_lines[prefix]:
        prefix += 1
    suffix = 0
    old_rest = len(old_lines) - prefix
    new_rest = len(new_lines) - prefix
    while (
        suffix < old_rest
        and suffix < new_rest
        and old_lines[-1 - suffix] == new_lines[-1 - suffix]
    ):
        suffix += 1
    added = len(new_lines) - prefix - suffix
    removed = len(old_lines) - prefix - suffix
    return added, removed


def changed(old: str, new: str) -> str:
    """Format a change summary as ``+{added}/-{removed}``."""
    added, removed = line_delta(old, new)
    return f"+{added}/-{removed}"


def _delta_lines(text: str) -> list[str]:
    stripped = text.rstrip("\n")
    if stripped == "":
        return []
    return stripped.split("\n")


def _without_trailing_blanks(lines: Sequence[str]) -> list[str]:
    end = len(lines)
    while end > 0 and is_blank_line(lines[end - 1]):
        end -= 1
    return list(lines[:end])


def _without_edge_blanks(lines: Sequence[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and is_blank_line(lines[start]):
        start += 1
    while end > start and is_blank_line(lines[end - 1]):
        end -= 1
    return list(lines[start:end])
