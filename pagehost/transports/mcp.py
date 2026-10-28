"""MCP transport. Read shaping and tool errors live here; edits do not."""

from __future__ import annotations

import json
import math
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from pagehost.application.api import PageService
from pagehost.config import Settings
from pagehost.domain.errors import PagehostError

# Appendix A for the markdown format, including the trailing newline of the block.
_MARKDOWN_INSTRUCTIONS = """\
Publish and edit web pages. Content format: markdown
Write the page body in Markdown. The platform adds the title (the only h1), layout and styling.
- Start headings at `##`. Headings define sections, which tools address by id (slug of the title).
- Supported: lists, tables, quotes, code, bold/italic/~~strike~~, links (http, https, mailto).
- Collapsible: a line `:::details Title`, body, then a line `:::`. Note box: `:::callout Title` ... `:::`.
- Not supported (removed or shown as text, with a warning): raw HTML, images, scripts, styles, forms.

Tools
- New content: append_page (no read needed). Pass section=<id> to add inside a section; to add
  a new sibling section, append to the section it follows with content starting at its heading.
- One phrase: replace_text with a short unique `old`; pass section to make short anchors unique.
- Rewrite a block: read_page(section=<id>), then replace_section (content includes the heading line).
- Remove a block: delete_section. Rewrite everything: replace_page.
- read_page on a big page returns an outline (section ids, sizes): fetch just what you need.
  Pass since=<version> to skip re-reading an unchanged page.
- Edit results give only the new version and "changed" line counts; don't re-read to verify.
- Errors list `candidates` (where `old` occurs, or the closest lines): fix and retry. Warnings mean
  something was altered or removed.
"""

_DESCRIPTIONS = {
    "publish_page": "Create a page. `title` is the heading; `content` is the body. Returns id and url.",
    "read_page": "Read a page. Big pages return an outline; use `section` (id) for one section or `full` for everything. `since` = last seen version: unchanged pages return no source.",
    "append_page": "Add content at the end of the page, or at the end of section `section`. No read needed.",
    "replace_text": "Replace one exact text. `old` must occur exactly once (in `section` if given).",
    "replace_section": "Replace a whole section with `content` (include its heading line). Don't quote the old text.",
    "delete_section": "Delete a section, including its subsections.",
    "replace_page": "Rewrite the whole page body (and optionally the title). Prefer the targeted tools.",
    "list_pages": "List pages (newest first), optionally filtered by a title/id substring.",
    "list_versions": "Most recent versions of a page (oldest first).",
    "rollback_page": "Restore an earlier version as a new version.",
    "delete_page": "Unpublish a page (history is kept).",
}

_OUTLINE_HINT = "Big page. Re-call with section=<id> or full=true."
_DROPPED_DETAILS = frozenset({"current_source", "edit_index"})


def build_mcp(service: PageService, settings: Settings) -> FastMCP:
    """FastMCP server named pagehost. Author of every edit is settings.mcp_author."""
    mcp = FastMCP("pagehost", instructions=_MARKDOWN_INSTRUCTIONS)
    author = settings.mcp_author

    @mcp.tool(description=_DESCRIPTIONS["publish_page"])
    def publish_page(title: str, content: str) -> dict[str, Any]:
        with _guard():
            published = service.publish(title, content, author=author)
            return _with_warnings(
                {"id": published.id, "url": published.url, "version": published.version},
                published.warnings,
            )

    @mcp.tool(description=_DESCRIPTIONS["read_page"])
    def read_page(
        id: str,
        section: str | None = None,
        full: bool = False,
        since: int | None = None,
    ) -> dict[str, Any]:
        with _guard():
            return _read_page(service, settings, id, section, full, since)

    @mcp.tool(description=_DESCRIPTIONS["append_page"])
    def append_page(id: str, content: str, section: str | None = None) -> dict[str, Any]:
        with _guard():
            return _mutation(service.append(id, content, section=section, author=author))

    @mcp.tool(description=_DESCRIPTIONS["replace_text"])
    def replace_text(
        id: str,
        old: str,
        new: str,
        section: str | None = None,
    ) -> dict[str, Any]:
        with _guard():
            return _mutation(
                service.replace_text(id, old, new, section=section, author=author)
            )

    @mcp.tool(description=_DESCRIPTIONS["replace_section"])
    def replace_section(id: str, section: str, content: str) -> dict[str, Any]:
        with _guard():
            return _mutation(
                service.replace_section(id, section, content, author=author)
            )

    @mcp.tool(description=_DESCRIPTIONS["delete_section"])
    def delete_section(id: str, section: str) -> dict[str, Any]:
        with _guard():
            return _mutation(service.delete_section(id, section, author=author))

    @mcp.tool(description=_DESCRIPTIONS["replace_page"])
    def replace_page(id: str, content: str, title: str | None = None) -> dict[str, Any]:
        with _guard():
            return _mutation(
                service.replace_page(id, content, title=title, author=author)
            )

    @mcp.tool(description=_DESCRIPTIONS["list_pages"])
    def list_pages(query: str | None = None, limit: int = 20) -> dict[str, Any]:
        with _guard():
            total, pages = service.list_pages(query=query, limit=_at_least_one(limit))
            return {
                "total": total,
                "pages": [
                    {"id": page.id, "title": page.title, "version": page.version, "url": page.url}
                    for page in pages
                ],
            }

    @mcp.tool(description=_DESCRIPTIONS["list_versions"])
    def list_versions(id: str, limit: int = 10) -> list[dict[str, Any]]:
        with _guard():
            versions = service.list_versions(id, limit=_at_least_one(limit))
            entries: list[dict[str, Any]] = []
            for version in versions:
                entry = {
                    "version": version.version,
                    "by": version.by,
                    "at": _format_at(version.at),
                }
                if version.summary:
                    entry["summary"] = version.summary
                entries.append(entry)
            return entries

    @mcp.tool(description=_DESCRIPTIONS["rollback_page"])
    def rollback_page(id: str, to_version: int) -> dict[str, Any]:
        with _guard():
            return _mutation(service.rollback(id, to_version, author=author))

    @mcp.tool(description=_DESCRIPTIONS["delete_page"])
    def delete_page(id: str) -> dict[str, Any]:
        with _guard():
            service.delete(id)
            return {"deleted": True}

    return mcp


def _read_page(
    service: PageService,
    settings: Settings,
    page_id: str,
    section: str | None,
    full: bool,
    since: int | None,
) -> dict[str, Any]:
    if section is not None:
        view = service.read_section(page_id, section)
        if since is not None and since == view.version:
            return {"version": view.version, "unchanged": True}
        return {"version": view.version, "section": view.section, "source": view.source}

    loaded = service.read_source(page_id)
    if since is not None and since == loaded.version:
        return {"version": loaded.version, "unchanged": True}
    if full or _estimated_tokens(loaded.source) <= settings.full_read_tokens:
        return {"version": loaded.version, "source": loaded.source}

    outline = service.outline(page_id)
    if not outline.sections:
        return {"version": loaded.version, "source": loaded.source}
    return {
        "version": outline.version,
        "tokens": outline.tokens,
        "outline": [
            f"{entry.id} h{entry.level} ~{entry.tokens}t" for entry in outline.sections
        ],
        "hint": _OUTLINE_HINT,
    }


def _estimated_tokens(source: str) -> int:
    return math.ceil(len(source) / 4)


def _at_least_one(limit: int) -> int:
    return limit if limit >= 1 else 1


def _format_at(moment: datetime) -> str:
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M")


def _mutation(result: Any) -> dict[str, Any]:
    return _with_warnings(
        {"version": result.version, "changed": result.changed},
        result.warnings,
    )


def _with_warnings(body: dict[str, Any], warnings: tuple[str, ...]) -> dict[str, Any]:
    if warnings:
        body["warnings"] = list(warnings)
    return body


def _tool_error(exc: PagehostError) -> ToolError:
    body = exc.as_dict()
    details = body.get("details")
    if isinstance(details, dict):
        kept = {key: value for key, value in details.items() if key not in _DROPPED_DETAILS}
        if kept:
            body["details"] = kept
        else:
            body.pop("details", None)
    return ToolError(json.dumps(body, separators=(",", ":")))


@contextmanager
def _guard():
    try:
        yield
    except PagehostError as exc:
        raise _tool_error(exc) from None
