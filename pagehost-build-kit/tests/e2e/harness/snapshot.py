"""Turn a served page into a *semantic snapshot*: what a reader would see, as data.

The snapshot ignores everything that is a rendering choice (classes, wrappers, whitespace,
stylesheets, footer, how a date is formatted) and keeps what is content or documented
semantics (headings, text, inline marks, lists, tables, and the components' data-* meaning).
Two implementations that serve the same page produce the same snapshot.

Inline marks are written as lightweight text: **strong**, *em*, `code`, ~~del~~, [text](href).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BLOCK = {"p", "div", "ul", "ol", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr",
         "section", "article", "aside", "details", "summary", "hr", "dl", "dt", "dd", "nav", "header",
         "footer", "figure", "main"}
HEADINGS = {f"h{i}" for i in range(1, 7)}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None] | None = None) -> None:
        self.tag, self.attrs, self.children = tag, dict(attrs or {}), []  # type: str, dict, list[Node | str]

    def find(self, tag: str, **attrs: str) -> "Node | None":
        return next(self.iter(tag, **attrs), None)

    def iter(self, tag: str | None = None, **attrs: str):
        for c in self.children:
            if isinstance(c, Node):
                if (tag is None or c.tag == tag) and all(c.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items()):
                    yield c
                yield from c.iter(tag, **attrs)

    def kids(self, tag: str | None = None) -> "list[Node]":
        return [c for c in self.children if isinstance(c, Node) and (tag is None or c.tag == tag)]


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(html: str) -> Node:
    b = _Builder()
    b.feed(html)
    b.close()
    return b.root


# ---- text ----------------------------------------------------------------------------------


def _clean(text: str) -> str:
    return re.sub(r" *\n *", "\n", text).strip()


def inline(node: Node) -> str:
    return _clean("".join(_inline_part(c) for c in node.children))


def _inline_part(c: "Node | str") -> str:
    if isinstance(c, str):
        return re.sub(r"\s+", " ", c)
    inner = "".join(_inline_part(x) for x in c.children)
    if c.tag in ("strong", "b"):
        return f"**{inner.strip()}**" if inner.strip() else ""
    if c.tag in ("em", "i"):
        return f"*{inner.strip()}*" if inner.strip() else ""
    if c.tag == "code":
        return f"`{inner}`"
    if c.tag in ("del", "s"):
        return f"~~{inner.strip()}~~"
    if c.tag == "a":
        return f"[{inner.strip()}]({c.attrs.get('href') or ''})"
    if c.tag == "br":
        return "\n"
    if c.tag in ("script", "style"):
        return ""
    return inner


def lines(node: Node, skip: "set[int] | None" = None) -> list[str]:
    """Visible text of a container, one entry per block, inline marks preserved."""
    skip = skip or set()
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        t = _clean("".join(run))
        if t:
            out.append(t)
        run.clear()

    def walk(n: Node) -> None:
        for c in n.children:
            if id(c) in skip:
                continue
            if isinstance(c, str):
                run.append(re.sub(r"\s+", " ", c))
            elif c.tag in BLOCK:
                flush()
                walk(c)
                flush()
            else:
                run.append(_inline_part(c))

    walk(node)
    flush()
    return out


def plain_text(node: Node) -> str:
    return re.sub(r"\s+", " ", "".join(_all_text(node))).strip()


def _all_text(n: "Node | str"):
    if isinstance(n, str):
        yield n
    elif n.tag not in ("script", "style"):
        for c in n.children:
            yield from _all_text(c)


# ---- blocks --------------------------------------------------------------------------------


def snapshot(html: str) -> dict[str, Any]:
    root = parse(html)
    main = root.find("main") or root.find("body") or root
    h1 = next((h for h in root.iter("h1") if not _inside(main, h)), None)
    title_tag = root.find("title")
    title = inline(h1) if h1 else (plain_text(title_tag) if title_tag else "")
    return {"title": title, "blocks": _blocks(main)}


def visible_text(html: str) -> str:
    root = parse(html)
    return plain_text(root.find("main") or root.find("body") or root)


def _inside(container: Node, target: Node) -> bool:
    return any(n is target for n in container.iter())


def _blocks(node: Node) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in node.children:
        if isinstance(c, str):
            if c.strip():
                out.append({"p": re.sub(r"\s+", " ", c).strip()})
            continue
        got = _block(c)
        out.extend(got if isinstance(got, list) else [got] if got else [])
    return out


def _block(n: Node):
    comp = n.attrs.get("data-component")
    if comp == "toc":
        return {"toc": [f"{inline(a)} -> {a.attrs.get('href', '')}" for a in n.iter("a")]}
    if comp == "stats":
        return {"stats": [_stat(d) for d in n.kids("div")]}
    if comp == "timeline":
        return {"timeline": [_milestone(li) for li in n.kids("li")]}
    if comp == "compare":
        return {"compare": [_option(a) for a in n.kids("article")]}
    if n.tag == "aside" or comp == "callout":
        return {"callout": _callout(n)}
    if n.tag in HEADINGS:
        t = inline(n)
        return {n.tag: t} if t else None
    if n.tag == "p":
        t = inline(n)
        return {"p": t} if t else None
    if n.tag in ("ul", "ol"):
        return {n.tag: _items(n)}
    if n.tag == "table":
        return {"table": _table(n)}
    if n.tag == "pre":
        return {"pre": "".join(_all_text(n)).rstrip("\n")}
    if n.tag == "blockquote":
        return {"blockquote": "\n".join(lines(n))}
    if n.tag == "hr":
        return {"hr": True}
    if n.tag == "details":
        summary = n.find("summary")
        body = lines(n, {id(summary)} if summary else None)
        out: dict[str, Any] = {"summary": inline(summary) if summary else "", "text": "\n".join(body)}
        if "open" in n.attrs:
            out["open"] = True
        return {"details": out}
    if n.tag == "dl":
        return {"dl": [[inline(c), ""] if c.tag == "dt" else ["", inline(c)] for c in n.kids() if c.tag in ("dt", "dd")]}
    if n.tag in ("script", "style", "br"):
        return None
    return _blocks(n)  # wrappers (div, section, article, figure, ...) are a rendering choice


def _items(lst: Node) -> list[Any]:
    items: list[Any] = []
    for li in lst.kids("li"):
        nested = [c for c in li.kids() if c.tag in ("ul", "ol")]
        text = "\n".join(lines(li, {id(c) for c in nested}))
        if nested:
            entry: dict[str, Any] = {"text": text}
            for c in nested:
                entry[c.tag] = _items(c)
            items.append(entry)
        else:
            items.append(text)
    return items


def _table(t: Node) -> dict[str, list]:
    def row(tr: Node) -> list[str]:
        return [" ".join(lines(c)) for c in tr.kids() if c.tag in ("th", "td")]

    thead, rows = t.find("thead"), [r for r in t.iter("tr")]
    head = row(thead.find("tr")) if thead and thead.find("tr") else []
    body = [row(r) for r in rows if not (thead and any(r is x for x in thead.iter("tr")))]
    if not head and body and rows and all(c.tag == "th" for c in rows[0].kids()):
        head, body = body[0], body[1:]
    return {"head": head, "rows": body}


def _callout(n: Node) -> dict[str, str]:
    first = next((c for c in n.children if isinstance(c, Node) or (isinstance(c, str) and c.strip())), None)
    title_node = first if isinstance(first, Node) and first.tag == "strong" else None
    out = {"kind": n.attrs.get("data-kind") or "note"}
    if title_node:
        out["title"] = inline(title_node)
    out["text"] = "\n".join(lines(n, {id(title_node)} if title_node else None))
    return out


def _stat(d: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, node in (("label", d.find("dt")), ("value", d.find("dd", data_role="value")),
                      ("delta", d.find("dd", data_role="delta"))):
        if node:
            out[key] = inline(node)
    if d.attrs.get("data-status"):
        out["status"] = d.attrs["data-status"]
    return out


def _milestone(li: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    when = li.find("time")
    if when:
        out["when"] = when.attrs.get("datetime") or inline(when)
    title = li.find("strong")
    if title:
        out["title"] = inline(title)
    if li.attrs.get("data-status"):
        out["status"] = li.attrs["data-status"]
    return out


def _option(a: Node) -> dict[str, Any]:
    h3 = a.find("h3")
    title = _clean("".join(_inline_part(c) for c in h3.children if not (isinstance(c, Node) and c.attrs.get("data-role") == "flag"))) if h3 else ""
    out: dict[str, Any] = {"title": title}
    if "data-recommended" in a.attrs:
        out["recommended"] = True
    p = a.find("p")
    if p:
        out["summary"] = inline(p)
    for key in ("pros", "cons"):
        ul = a.find("ul", data_role=key)
        out[key] = [inline(li) for li in ul.kids("li")] if ul else []
    return out


# ---- invariants ----------------------------------------------------------------------------

FORBIDDEN_TAGS = {"script", "style", "iframe", "object", "embed", "svg", "math", "form", "input", "button",
                  "textarea", "select", "video", "audio", "base", "meta_refresh"}
URL_ATTRS = {"href", "src", "action", "formaction", "data", "poster", "srcset"}


def _relative(url: str) -> bool:
    u = url.strip().lower()
    return not re.match(r"^[a-z][a-z0-9+.-]*:", u) and not u.startswith("//")


def inert_violations(html: str) -> list[str]:
    """Anything in a served page that could run code or load something from elsewhere."""
    out: list[str] = []
    for n in parse(html).iter():
        t, a = n.tag, n.attrs
        if t in FORBIDDEN_TAGS:
            out.append(f"<{t}> element")
        if t == "link" and not (a.get("rel") == "stylesheet" and _relative(a.get("href") or "")):
            out.append("<link> that is not a same-origin stylesheet")
        if t == "img" and not _relative(a.get("src") or ""):
            out.append("<img> loading an external/inline source")
        if t == "meta" and (a.get("http-equiv") or "").lower() == "refresh":
            out.append("meta refresh")
        for k, v in a.items():
            if k.startswith("on"):
                out.append(f"event handler attribute {k} on <{t}>")
            if k == "style":
                out.append(f"inline style on <{t}>")
            if k in URL_ATTRS and v and re.match(r"^\s*(javascript|vbscript|data):", v, re.I):
                out.append(f"{k}={v[:30]!r} on <{t}>")
    return out
