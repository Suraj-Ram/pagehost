"""Wrap a sanitized fragment in the page shell and serve the shared stylesheet."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from pagehost.domain.models import Document, TocHeading

_STYLESHEET = Path(__file__).resolve().parent.parent / "assets" / "pagehost.css"
_MINIMUM_HEADINGS = 5


class PagehostTheme:
    def render_document(self, document: Document) -> str:
        title = escape(document.title, quote=True)
        updated = _utc_stamp(document.updated_at)
        contents = _table_of_contents(document.toc)
        header = f"<header><h1>{title}</h1>"
        if contents:
            header += f"\n{contents}"
        header += "</header>\n"
        return (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="color-scheme" content="light dark">\n'
            f"<title>{title}</title>\n"
            '<link rel="stylesheet" href="/_assets/pagehost.css">\n'
            "</head>\n"
            "<body>\n"
            f"{header}"
            "<main>\n"
            f"{document.body_html}\n"
            "</main>\n"
            f"<footer>v{document.version} &middot; updated {updated}</footer>\n"
            "</body>\n"
            "</html>\n"
        )

    def static_assets(self) -> dict[str, bytes]:
        return {"pagehost.css": _STYLESHEET.read_bytes()}


class _TocNode:
    def __init__(self, heading: TocHeading) -> None:
        self.id = heading.id
        self.title = heading.title
        self.children: list[_TocNode] = []


def _table_of_contents(headings: Sequence[TocHeading]) -> str:
    """Contents of the page, nested by markdown heading level.

    Level comes from the source (`#` is 1, `##` is 2), including a level-1
    heading the body renders as h2 because the page title is the document h1.
    Fewer than five headings leave the list out.
    """
    if len(headings) < _MINIMUM_HEADINGS:
        return ""
    return (
        '<nav data-component="toc" aria-label="Contents">\n'
        '<p data-role="label">On this page</p>\n'
        f"{_toc_list(_toc_tree(headings), ordered=True)}"
        "</nav>\n"
    )


def _toc_tree(headings: Sequence[TocHeading]) -> list[_TocNode]:
    roots: list[_TocNode] = []
    stack: list[tuple[int, _TocNode]] = []
    for heading in headings:
        node = _TocNode(heading)
        while stack and stack[-1][0] >= heading.level:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((heading.level, node))
    return roots


def _toc_list(nodes: Sequence[_TocNode], *, ordered: bool) -> str:
    # Nested lists are unordered. The contents stylesheet turns every ordered
    # list into a grid, which would place a child beside its parent.
    tag = "ol" if ordered else "ul"
    lines = [f"<{tag}>\n"]
    for node in nodes:
        href = escape(f"#{node.id}", quote=True)
        label = escape(node.title)
        children = _toc_list(node.children, ordered=False) if node.children else ""
        lines.append(f'<li><a href="{href}">{label}</a>{children}</li>\n')
    lines.append(f"</{tag}>\n")
    return "".join(lines)


def _utc_stamp(updated_at: datetime) -> str:
    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone(timezone.utc)
    return updated_at.strftime("%Y-%m-%d %H:%M UTC")
