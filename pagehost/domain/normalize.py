"""Input normalisation applied before any other domain rule. SPEC §3.2."""

from __future__ import annotations

from pagehost.domain.errors import ContentTooLarge, InvalidContent

_MAX_TITLE_LENGTH = 200


def normalize_newlines(text: str) -> str:
    """Convert CRLF and lone CR to LF.

    CRLF is replaced first so a carriage return that belongs to a pair does not
    become its own newline.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_title(title: str) -> str:
    """Trim a title. Empty or longer than 200 characters is invalid content."""
    trimmed = title.strip()
    if not trimmed:
        raise InvalidContent("title is empty")
    if len(trimmed) > _MAX_TITLE_LENGTH:
        raise InvalidContent("title is longer than 200 characters")
    return trimmed


def ensure_source_size(source: str, max_bytes: int) -> int:
    """Return the UTF-8 size of source, or raise if it exceeds max_bytes."""
    size = len(source.encode("utf-8"))
    if size > max_bytes:
        raise ContentTooLarge(f"source is {size} bytes; limit is {max_bytes}")
    return size
