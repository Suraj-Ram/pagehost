"""Operations a scenario applies, in order, to one page.

Scenarios live in `tests/acceptance/cases.py`. Each value in `Scenario.operations`
is one MCP tool call. The driver supplies the page id.

| Class | Tool |
| --- | --- |
| `Publish` | `publish_page` |
| `Append` | `append_page` |
| `ReplaceText` | `replace_text` |
| `ReplaceSection` | `replace_section` |
| `DeleteSection` | `delete_section` |
| `ReplacePage` | `replace_page` |
| `Rollback` | `rollback_page` |
| `DeletePage` | `delete_page` |

`Scenario.blocks` is the semantic HTML a reader should see. Inline marks are
text (`**strong**`, `*em*`, `` `code` ``, `~~del~~`, `[text](href)`).
Stylesheets, classes, wrappers, and the page shell are left out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias


@dataclass(frozen=True, slots=True)
class Publish:
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class Append:
    content: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class ReplaceText:
    old: str
    new: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class ReplaceSection:
    section: str
    content: str


@dataclass(frozen=True, slots=True)
class DeleteSection:
    section: str


@dataclass(frozen=True, slots=True)
class ReplacePage:
    content: str
    title: str | None = None


@dataclass(frozen=True, slots=True)
class Rollback:
    to_version: int


@dataclass(frozen=True, slots=True)
class DeletePage:
    pass


Operation: TypeAlias = (
    Publish | Append | ReplaceText | ReplaceSection | DeleteSection | ReplacePage | Rollback | DeletePage
)
Block: TypeAlias = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Scenario:
    """One page, built by `operations`, judged by what a reader would see."""

    name: str
    operations: tuple[Operation, ...]
    blocks: tuple[Block, ...]
    title: str | None = None
