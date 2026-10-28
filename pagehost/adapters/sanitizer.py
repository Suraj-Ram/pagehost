"""Allowlist HTML sanitizer. Appendix D of the spec."""

from __future__ import annotations

import nh3

from pagehost.domain.ports import HtmlSanitizer

# Closed lists. A tag that is not listed is dropped and its text is kept.
# script and style are removed together with their content.
_TAGS = {
    "a",
    "abbr",
    "article",
    "aside",
    "blockquote",
    "br",
    "caption",
    "code",
    "dd",
    "del",
    "details",
    "div",
    "dl",
    "dt",
    "em",
    "figcaption",
    "figure",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "ins",
    "kbd",
    "li",
    "mark",
    "nav",
    "ol",
    "p",
    "pre",
    "s",
    "section",
    "small",
    "span",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "time",
    "tr",
    "ul",
}

_GLOBAL_ATTRIBUTES = {
    "aria-label",
    "data-align",
    "data-component",
    "data-kind",
    "data-recommended",
    "data-role",
    "data-status",
    "id",
    "lang",
    "title",
}

# "*" applies to every tag. Tag entries add attributes; they do not replace the globals.
# data-* is this explicit set, never a prefix wildcard.
_ATTRIBUTES = {
    "*": set(_GLOBAL_ATTRIBUTES),
    "a": {"href"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
    "ol": {"start"},
    "details": {"open"},
    "time": {"datetime"},
}

_URL_SCHEMES = {"http", "https", "mailto"}

_CLEANER = nh3.Cleaner(
    tags=_TAGS,
    clean_content_tags={"script", "style"},
    attributes=_ATTRIBUTES,
    url_schemes=_URL_SCHEMES,
    strip_comments=True,
    link_rel="noopener noreferrer",
    generic_attribute_prefixes=set(),
    url_relative="pass_through",
)


class Nh3Sanitizer(HtmlSanitizer):
    """HtmlSanitizer backed by an nh3 allowlist."""

    def clean(self, html: str) -> str:
        return _CLEANER.clean(html)
