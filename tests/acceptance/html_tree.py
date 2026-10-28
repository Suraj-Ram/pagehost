"""A small HTML tree. Attributes other than the ones the snapshot reads are ignored."""

from __future__ import annotations

from html.parser import HTMLParser

VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
})


class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None] | None = None) -> None:
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children: list[Node | str] = []

    def find(self, tag: str, **attrs: str) -> Node | None:
        return next(self.iter(tag, **attrs), None)

    def iter(self, tag: str | None = None, **attrs: str):
        for child in self.children:
            if not isinstance(child, Node):
                continue
            if (tag is None or child.tag == tag) and _attrs_match(child, attrs):
                yield child
            yield from child.iter(tag, **attrs)

    def kids(self, tag: str | None = None) -> list[Node]:
        return [
            child for child in self.children
            if isinstance(child, Node) and (tag is None or child.tag == tag)
        ]


def _attrs_match(node: Node, attrs: dict[str, str]) -> bool:
    return all(node.attrs.get(key.replace("_", "-")) == value for key, value in attrs.items())


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, dict(attrs))
        self._stack[-1].children.append(node)
        if tag not in VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def parse(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root
