"""Markdown content format: CommonMark, GFM tables and strikethrough, three directives."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import re
from typing import Any
from urllib.parse import urlparse

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.rules_inline import image as parse_image
from markdown_it.token import Token
from mdit_py_plugins.container import container_plugin

from pagehost.domain.errors import InvalidContent
from pagehost.domain.models import Heading, RenderedFragment
from pagehost.domain.ports import HtmlSanitizer

_H1_WARNING = "Level-1 headings were demoted to level 2; the page title is the h1."
_HTML_WARNING = "Raw HTML is not supported and is shown as literal text."
_IMAGE_WARNING = "Images are not supported and were removed."
_DIRECTIVE_WARNING = (
    "Found ':::' text that is not a valid directive (supported: details, callout)."
)

# Appendix A, after the format line, through the Tools section.
_AUTHORING_GUIDE = """\
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

_ALLOWED_SCHEMES = frozenset({"http", "https", "mailto"})
_TAG_LIKE = re.compile(
    r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^>\n]*|/?>|>)|<!--|<!\[CDATA\[|<\?|<!DOCTYPE",
    re.IGNORECASE,
)
_SUPPRESS_OPEN = frozenset({
    "blockquote_open",
    "bullet_list_open",
    "ordered_list_open",
})
_SUPPRESS_CLOSE = frozenset({
    "blockquote_close",
    "bullet_list_close",
    "ordered_list_close",
})
_STATUS_LABELS = {
    "done": "Done",
    "active": "Active",
    "at-risk": "At risk",
    "blocked": "Blocked",
    "planned": "Planned",
}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_QUOTE_ONLY = re.compile(r"\s*(?:>\s*)+")


class MarkdownFormat:
    """CommonMark body renderer. The page title is the document's only h1."""

    name = "markdown"

    def __init__(self, sanitizer: HtmlSanitizer) -> None:
        self._sanitizer = sanitizer
        self._md = _Parser()

    def render(self, source: str) -> RenderedFragment:
        tokens, env = self._parse(source)
        warnings: list[str] = []
        _rewrite(tokens, warnings, source)
        try:
            html = self._md.renderer.render(tokens, self._md.options, env)
        except Exception as exc:
            raise InvalidContent("Markdown could not be compiled.") from exc
        return RenderedFragment(html=self._sanitizer.clean(html), warnings=tuple(warnings))

    def authoring_guide(self) -> str:
        return _AUTHORING_GUIDE

    def headings(self, source: str) -> tuple[Heading, ...]:
        tokens, _env = self._parse(source)
        return tuple(_headings(tokens))

    def _parse(self, source: str) -> tuple[list[Token], dict[str, Any]]:
        env: dict[str, Any] = {}
        try:
            tokens = self._md.parse(source, env)
        except Exception as exc:
            raise InvalidContent("Markdown could not be compiled.") from exc
        return tokens, env


class _Parser(MarkdownIt):
    def __init__(self) -> None:
        super().__init__(
            "js-default",
            {"html": False, "linkify": False, "typographer": False},
        )
        self._image_depth = 0
        self.enable(("table", "strikethrough"))
        self.inline.ruler.at("image", _parse_image)
        self.add_render_rule("image", _render_removed_image)
        self.use(container_plugin, "details", render=_render_details)
        self.use(container_plugin, "callout", render=_render_callout)
        self.use(container_plugin, "timeline", render=_render_timeline)

    def validateLink(self, url: str) -> bool:
        # Image destinations are parsed, then dropped. Link schemes stay strict.
        if self._image_depth:
            return True
        return _allowed_url(url)


def _parse_image(state: Any, silent: bool) -> bool:
    parser: _Parser = state.md
    parser._image_depth += 1
    try:
        return parse_image(state, silent)
    finally:
        parser._image_depth -= 1


def _allowed_url(url: str) -> bool:
    candidate = url.strip()
    if not candidate or candidate.startswith("#"):
        return True
    parsed = urlparse(candidate)
    if parsed.scheme:
        return parsed.scheme.lower() in _ALLOWED_SCHEMES
    if candidate.startswith("//") or parsed.netloc:
        return False
    return True


def _render_details(
    self: Any,
    tokens: Sequence[Token],
    idx: int,
    _options: object,
    _env: object,
) -> str:
    if tokens[idx].nesting != 1:
        return "</details>\n"
    title = _directive_title(tokens[idx].info, "details") or "Details"
    return f"<details><summary>{escapeHtml(title)}</summary>\n"


def _render_callout(
    self: Any,
    tokens: Sequence[Token],
    idx: int,
    _options: object,
    _env: object,
) -> str:
    if tokens[idx].nesting != 1:
        return "</aside>\n"
    title = _directive_title(tokens[idx].info, "callout")
    head = f"<strong>{escapeHtml(title)}</strong>\n" if title else ""
    return f'<aside data-component="callout" data-kind="note">\n{head}'


def _directive_title(info: str, name: str) -> str:
    parts = info.strip().split(maxsplit=1)
    if not parts or parts[0] != name:
        return ""
    if len(parts) == 1:
        return ""
    return parts[1].strip()


def _render_timeline(
    self: Any,
    tokens: Sequence[Token],
    idx: int,
    _options: object,
    _env: object,
) -> str:
    if tokens[idx].nesting != 1:
        return ""
    meta = tokens[idx].meta or {}
    return str(meta.get("html", ""))


def _rewrite(tokens: list[Token], warnings: list[str], source: str) -> None:
    paragraph = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "container_timeline_open":
            close = _container_close(tokens, index)
            token.meta = {"html": _timeline_html(_directive_body(source, token), warnings)}
            # Drop the parsed body. Line syntax is rendered from the source, and
            # an inline token still emits its children when it is only marked hidden.
            del tokens[index + 1 : close]
            paragraph = False
            index += 1
            continue
        if token.type in {"heading_open", "heading_close"} and token.tag == "h1":
            if token.type == "heading_open":
                _remember(warnings, _H1_WARNING)
            token.tag = "h2"
        if token.type == "paragraph_open":
            paragraph = True
            index += 1
            continue
        if token.type == "inline":
            _scan_inline(token, warnings, paragraph=paragraph)
        paragraph = False
        index += 1


def _container_close(tokens: Sequence[Token], open_at: int) -> int:
    depth = 0
    for index in range(open_at, len(tokens)):
        if tokens[index].type == "container_timeline_open":
            depth += 1
        elif tokens[index].type == "container_timeline_close":
            depth -= 1
            if depth == 0:
                return index
    return len(tokens)


def _directive_body(source: str, token: Token) -> list[str]:
    if not token.map:
        return []
    lines = source.splitlines()
    start, end = token.map
    if start >= len(lines):
        return []
    marker = lines[start].find(":::")
    prefix = lines[start][:marker] if marker >= 0 else ""
    body: list[str] = []
    for line in lines[start + 1 : end]:
        if prefix and line.startswith(prefix):
            line = line[len(prefix) :]
        body.append(line)
    return body


def _timeline_html(lines: list[str], warnings: list[str]) -> str:
    pieces: list[str] = []
    items: list[str] = []
    row = 0

    def flush() -> None:
        if items:
            pieces.append('<ol data-component="timeline">\n' + "".join(items) + "</ol>\n")
            items.clear()

    for line in lines:
        if not line.strip() or _QUOTE_ONLY.fullmatch(line):
            continue
        row += 1
        item = _timeline_item(line.strip(), row, warnings)
        if item is None:
            flush()
            pieces.append(f"<p>{escapeHtml(line.strip())}</p>\n")
            continue
        items.append(item)
    flush()
    if not pieces:
        return '<ol data-component="timeline">\n</ol>\n'
    return "".join(pieces)


def _timeline_item(line: str, row: int, warnings: list[str]) -> str | None:
    parts = [part.strip() for part in line.split("|", 2)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        _remember(warnings, f'timeline row {row} needs "date | title"; shown as plain text')
        return None
    when, title = parts[0], parts[1]
    status = parts[2] if len(parts) == 3 else ""
    attrs = ""
    badge = ""
    if status:
        label = _STATUS_LABELS.get(status)
        if label is None:
            _remember(
                warnings,
                "timeline row "
                f"{row}: unknown status {status!r}; use done|active|at-risk|blocked|planned",
            )
        else:
            attrs = f' data-status="{status}"'
            badge = f'<span data-role="status">{label}</span>'
    shown = _display_date(when)
    if shown is None:
        time = f"<time>{escapeHtml(when)}</time>"
    else:
        time = f'<time datetime="{when}">{shown}</time>'
    return f"<li{attrs}>{time}\n<strong>{escapeHtml(title)}</strong>{badge}</li>\n"


def _display_date(value: str) -> str | None:
    if _ISO_DATE.fullmatch(value) is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return f"{_MONTHS[parsed.month - 1]} {parsed.day}, {parsed.year}"


def _scan_inline(token: Token, warnings: list[str], *, paragraph: bool) -> None:
    at_line_start = True
    for child in token.children or []:
        if child.type in {"softbreak", "hardbreak"}:
            at_line_start = True
            continue
        if child.type == "image":
            _remember(warnings, _IMAGE_WARNING)
            at_line_start = False
            continue
        if child.type == "text":
            _scan_text(child.content, warnings, at_line_start=at_line_start, paragraph=paragraph)
            if child.content:
                at_line_start = False
            continue
        at_line_start = False


def _scan_text(content: str, warnings: list[str], *, at_line_start: bool, paragraph: bool) -> None:
    for index, piece in enumerate(content.split("\n")):
        if paragraph and (at_line_start if index == 0 else True) and piece.startswith(":::"):
            _remember(warnings, _DIRECTIVE_WARNING)
        if _TAG_LIKE.search(piece):
            _remember(warnings, _HTML_WARNING)


def _remember(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


def _headings(tokens: list[Token]) -> list[Heading]:
    found: list[Heading] = []
    depth = 0
    for index, token in enumerate(tokens):
        delta = _suppress_delta(token.type)
        if delta:
            depth = max(0, depth + delta)
            continue
        if depth or token.type != "heading_open":
            continue
        title = ""
        if index + 1 < len(tokens) and tokens[index + 1].type == "inline":
            title = _plain_text(tokens[index + 1])
        line = token.map[0] if token.map else 0
        found.append(Heading(level=int(token.tag[1:]), title=title, line=line))
    return found


def _suppress_delta(token_type: str) -> int:
    if token_type in _SUPPRESS_OPEN or (
        token_type.startswith("container_") and token_type.endswith("_open")
    ):
        return 1
    if token_type in _SUPPRESS_CLOSE or (
        token_type.startswith("container_") and token_type.endswith("_close")
    ):
        return -1
    return 0


def _plain_text(token: Token) -> str:
    parts: list[str] = []

    def walk(node: Token) -> None:
        if node.type in {"text", "code_inline"}:
            parts.append(node.content)
            return
        for child in node.children or []:
            walk(child)

    for child in token.children or []:
        walk(child)
    return "".join(parts)


def _render_removed_image(
    self: Any,
    tokens: Sequence[Token],
    idx: int,
    _options: object,
    _env: object,
) -> str:
    return ""
