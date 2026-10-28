"""Reduce HTML to the content a reader sees.

Classes, stylesheets, wrappers, the page shell, and the footer are rendering
choices and do not appear in the result. Inline marks are written as text:
**strong**, *em*, `code`, ~~del~~, [text](href).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from acceptance.html_tree import Node, parse
from acceptance.operations import Block

_BLOCK_TAGS = frozenset({
    "p", "div", "ul", "ol", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "tr", "section", "article", "aside", "details", "summary", "hr", "dl", "dt", "dd",
    "nav", "header", "footer", "figure", "main",
})
_HEADINGS = frozenset(f"h{level}" for level in range(1, 7))


@dataclass(frozen=True, slots=True)
class SemanticView:
    title: str
    blocks: tuple[Block, ...]


def semantic_view(html: str) -> SemanticView:
    """Snapshot a fragment or a full document. A `<main>` element scopes the blocks."""
    root = parse(html)
    main = root.find("main") or root.find("body") or root
    heading = next((node for node in root.iter("h1") if not _inside(main, node)), None)
    title_tag = root.find("title")
    title = inline(heading) if heading is not None else (plain_text(title_tag) if title_tag else "")
    return SemanticView(title=title, blocks=tuple(_blocks(main)))


def assert_semantic(
    html: str,
    blocks: Sequence[Mapping[str, Any]],
    *,
    title: str | None = None,
) -> None:
    """Fail if `html` does not have this title and these content blocks."""
    __tracebackhide__ = True
    view = semantic_view(html)
    if title is not None:
        assert view.title == title
    assert view.blocks == tuple(blocks)


def inline(node: Node) -> str:
    return _clean("".join(_inline_part(child) for child in node.children))


def plain_text(node: Node | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", "".join(_all_text(node))).strip()


def _blocks(node: Node) -> list[Block]:
    blocks: list[Block] = []
    for child in node.children:
        if isinstance(child, str):
            text = re.sub(r"\s+", " ", child).strip()
            if text:
                blocks.append({"p": text})
            continue
        got = _block(child)
        if got is None:
            continue
        blocks.extend(got if isinstance(got, list) else [got])
    return blocks


def _block(node: Node) -> Block | list[Block] | None:
    component = node.attrs.get("data-component")
    if component == "toc":
        return {"toc": [f"{inline(link)} -> {link.attrs.get('href', '')}" for link in node.iter("a")]}
    if component == "stats":
        return {"stats": [_stat(row) for row in node.kids("div")]}
    if component == "timeline":
        return {"timeline": [_milestone(item) for item in node.kids("li")]}
    if component == "compare":
        return {"compare": [_option(article) for article in node.kids("article")]}
    if node.tag == "aside" or component == "callout":
        return {"callout": _callout(node)}
    if node.tag in _HEADINGS:
        text = inline(node)
        return {node.tag: text} if text else None
    if node.tag == "p":
        text = inline(node)
        return {"p": text} if text else None
    if node.tag in ("ul", "ol"):
        return {node.tag: _items(node)}
    if node.tag == "table":
        return {"table": _table(node)}
    if node.tag == "pre":
        return {"pre": "".join(_all_text(node)).rstrip("\n")}
    if node.tag == "blockquote":
        return {"blockquote": "\n".join(_lines(node))}
    if node.tag == "hr":
        return {"hr": True}
    if node.tag == "details":
        return {"details": _details(node)}
    if node.tag == "dl":
        pairs = [
            [inline(child), ""] if child.tag == "dt" else ["", inline(child)]
            for child in node.kids()
            if child.tag in ("dt", "dd")
        ]
        return {"dl": pairs}
    if node.tag in ("script", "style", "br"):
        return None
    return _blocks(node)


def _items(lst: Node) -> list[Any]:
    items: list[Any] = []
    for item in lst.kids("li"):
        nested = [child for child in item.kids() if child.tag in ("ul", "ol")]
        text = "\n".join(_lines(item, {id(child) for child in nested}))
        if not nested:
            items.append(text)
            continue
        entry: dict[str, Any] = {"text": text}
        for child in nested:
            entry[child.tag] = _items(child)
        items.append(entry)
    return items


def _table(table: Node) -> dict[str, list[Any]]:
    def row(tr: Node) -> list[str]:
        return [" ".join(_lines(cell)) for cell in tr.kids() if cell.tag in ("th", "td")]

    head_row = table.find("thead")
    head_tr = head_row.find("tr") if head_row is not None else None
    all_rows = list(table.iter("tr"))
    head = row(head_tr) if head_tr is not None else []
    body = [
        row(tr) for tr in all_rows
        if head_row is None or not any(tr is candidate for candidate in head_row.iter("tr"))
    ]
    if not head and body and all_rows and all(cell.tag == "th" for cell in all_rows[0].kids()):
        head, body = body[0], body[1:]
    return {"head": head, "rows": body}


def _callout(node: Node) -> dict[str, str]:
    first = next(
        (child for child in node.children if isinstance(child, Node) or (isinstance(child, str) and child.strip())),
        None,
    )
    title_node = first if isinstance(first, Node) and first.tag == "strong" else None
    callout = {"kind": node.attrs.get("data-kind") or "note"}
    if title_node is not None:
        callout["title"] = inline(title_node)
    callout["text"] = "\n".join(_lines(node, {id(title_node)} if title_node is not None else None))
    return callout


def _details(node: Node) -> dict[str, Any]:
    summary = node.find("summary")
    body = _lines(node, {id(summary)} if summary is not None else None)
    details: dict[str, Any] = {
        "summary": inline(summary) if summary is not None else "",
        "text": "\n".join(body),
    }
    if "open" in node.attrs:
        details["open"] = True
    return details


def _stat(row: Node) -> dict[str, str]:
    stat: dict[str, str] = {}
    fields = (
        ("label", row.find("dt")),
        ("value", row.find("dd", data_role="value")),
        ("delta", row.find("dd", data_role="delta")),
    )
    for key, child in fields:
        if child is not None:
            stat[key] = inline(child)
    status = row.attrs.get("data-status")
    if status:
        stat["status"] = status
    return stat


def _milestone(item: Node) -> dict[str, str]:
    milestone: dict[str, str] = {}
    when = item.find("time")
    if when is not None:
        milestone["when"] = when.attrs.get("datetime") or inline(when)
    title = item.find("strong")
    if title is not None:
        milestone["title"] = inline(title)
    status = item.attrs.get("data-status")
    if status:
        milestone["status"] = status
    return milestone


def _option(article: Node) -> dict[str, Any]:
    heading = article.find("h3")
    if heading is None:
        title = ""
    else:
        title = _clean("".join(
            _inline_part(child)
            for child in heading.children
            if not (isinstance(child, Node) and child.attrs.get("data-role") == "flag")
        ))
    option: dict[str, Any] = {"title": title}
    if "data-recommended" in article.attrs:
        option["recommended"] = True
    summary = article.find("p")
    if summary is not None:
        option["summary"] = inline(summary)
    for key in ("pros", "cons"):
        listed = article.find("ul", data_role=key)
        option[key] = [inline(item) for item in listed.kids("li")] if listed is not None else []
    return option


def _lines(node: Node, skip: set[int] | None = None) -> list[str]:
    skipped = skip or set()
    lines: list[str] = []
    run: list[str] = []

    def flush() -> None:
        text = _clean("".join(run))
        if text:
            lines.append(text)
        run.clear()

    def walk(current: Node) -> None:
        for child in current.children:
            if id(child) in skipped:
                continue
            if isinstance(child, str):
                run.append(re.sub(r"\s+", " ", child))
            elif child.tag in _BLOCK_TAGS:
                flush()
                walk(child)
                flush()
            else:
                run.append(_inline_part(child))

    walk(node)
    flush()
    return lines


def _inline_part(child: Node | str) -> str:
    if isinstance(child, str):
        return re.sub(r"\s+", " ", child)
    inner = "".join(_inline_part(part) for part in child.children)
    if child.tag in ("strong", "b"):
        return f"**{inner.strip()}**" if inner.strip() else ""
    if child.tag in ("em", "i"):
        return f"*{inner.strip()}*" if inner.strip() else ""
    if child.tag == "code":
        return f"`{inner}`"
    if child.tag in ("del", "s"):
        return f"~~{inner.strip()}~~"
    if child.tag == "a":
        return f"[{inner.strip()}]({child.attrs.get('href') or ''})"
    if child.tag == "br":
        return "\n"
    if child.tag in ("script", "style"):
        return ""
    return inner


def _all_text(node: Node | str):
    if isinstance(node, str):
        yield node
        return
    if node.tag in ("script", "style"):
        return
    for child in node.children:
        yield from _all_text(child)


def _inside(container: Node, target: Node) -> bool:
    return any(node is target for node in container.iter())


def _clean(text: str) -> str:
    return re.sub(r" *\n *", "\n", text).strip()
