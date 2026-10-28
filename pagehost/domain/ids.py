"""Page id pattern and allocation. SPEC §3.3."""

from __future__ import annotations

import re
import secrets
from typing import Callable

from pagehost.domain.errors import PageExists

_PAGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_SLUG_LIMIT = 40
_ALLOCATION_ATTEMPTS = 5


def is_valid_page_id(page_id: str) -> bool:
    """Return whether page_id matches the public id pattern."""
    return _PAGE_ID.fullmatch(page_id) is not None


def slug_title(title: str) -> str:
    """Turn a title into the slug half of a page id.

    Lowercase, collapse every run outside ``[a-z0-9]`` to ``-``, trim hyphens,
    truncate to 40 characters, and trim hyphens again. An empty result is ``page``.
    """
    collapsed = _NON_SLUG.sub("-", title.lower()).strip("-")
    # Truncation can cut a separator and leave a trailing hyphen.
    slug = collapsed[:_SLUG_LIMIT].strip("-")
    return slug or "page"


def allocate_page_id(title: str, taken: Callable[[str], bool]) -> str:
    """Return ``{slug}-{6 lowercase hex}``, retrying while ``taken`` is true.

    ``taken`` reports whether a candidate id is already used. After five taken
    ids, allocation fails with ``page_exists``.
    """
    slug = slug_title(title)
    for _ in range(_ALLOCATION_ATTEMPTS):
        page_id = f"{slug}-{secrets.token_hex(3)}"
        if not taken(page_id):
            return page_id
    raise PageExists(f"could not allocate a unique page id for {slug!r}")
