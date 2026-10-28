"""Markdown format: render warnings, directives, and top-level headings."""

from __future__ import annotations

from pathlib import Path

from acceptance.cases import MARKDOWN_FEATURE_TOUR
from acceptance.operations import Publish
from acceptance.semantic import assert_semantic

from pagehost.adapters.markdown import MarkdownFormat
from pagehost.domain.errors import InvalidContent
from pagehost.domain.models import Heading

_H1 = "Level-1 headings were demoted to level 2; the page title is the h1."
_HTML = "Raw HTML is not supported and is shown as literal text."
_IMAGE = "Images are not supported and were removed."
_DIRECTIVE = "Found ':::' text that is not a valid directive (supported: details, callout)."


class RecordingSanitizer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def clean(self, html: str) -> str:
        self.calls.append(html)
        return html


def _format() -> tuple[MarkdownFormat, RecordingSanitizer]:
    sanitizer = RecordingSanitizer()
    return MarkdownFormat(sanitizer), sanitizer


def _guide_from_spec() -> str:
    spec = Path(__file__).resolve().parents[2] / "pagehost-build-kit" / "SPEC.md"
    appendix = spec.read_text(encoding="utf-8").split("## Appendix A:", 1)[1]
    fenced = appendix.split("```text\n", 1)[1].split("```", 1)[0]
    first, _, rest = fenced.partition("\n")
    assert first == "Publish and edit web pages. Content format: markdown"
    return rest


def test_clean_is_called_and_its_result_is_returned():
    class Stamp(RecordingSanitizer):
        def clean(self, html: str) -> str:
            self.calls.append(html)
            return html + "<!--clean-->"

    stamp = Stamp()
    result = MarkdownFormat(stamp).render("Hello\n")

    assert stamp.calls == ["<p>Hello</p>\n"]
    assert result.html == "<p>Hello</p>\n<!--clean-->"
    assert result.warnings == ()


def test_authoring_guide_is_appendix_a_after_the_format_line():
    fmt, sanitizer = _format()

    assert fmt.name == "markdown"
    assert fmt.authoring_guide() == _guide_from_spec()
    assert sanitizer.calls == []


def test_level_one_headings_are_demoted_once():
    fmt, sanitizer = _format()

    result = fmt.render("# Title\n\n# Again\n\n## Kept\n")

    assert "<h1" not in result.html
    assert result.html.count("<h2>") == 3
    assert "<h2>Title</h2>" in result.html
    assert "<h2>Kept</h2>" in result.html
    assert result.warnings == (_H1,)
    assert sanitizer.calls == [result.html]
    assert fmt.headings("# Title\n\n## Kept\n") == (
        Heading(1, "Title", 0),
        Heading(2, "Kept", 2),
    )
    assert sanitizer.calls == [result.html]


def test_setext_h1_is_demoted_in_html_and_kept_in_headings():
    fmt, _sanitizer = _format()
    source = "Title\n=====\n"

    result = fmt.render(source)

    assert "<h1" not in result.html
    assert "<h2>Title</h2>" in result.html
    assert result.warnings == (_H1,)
    assert fmt.headings(source) == (Heading(1, "Title", 0),)


def test_raw_html_is_literal_text():
    fmt, sanitizer = _format()

    result = fmt.render("<b>x</b>\n")

    assert result.html == "<p>&lt;b&gt;x&lt;/b&gt;</p>\n"
    assert "<b>" not in result.html
    assert result.warnings == (_HTML,)
    assert sanitizer.calls == [result.html]


def test_images_are_removed():
    fmt, _sanitizer = _format()

    removed = fmt.render("![logo](https://evil.example/logo.png)\n")
    hostile = fmt.render("![logo](javascript:alert(1))\n")
    kept = fmt.render("See ![logo](https://evil.example/logo.png) here\n")

    assert removed.html == "<p></p>\n"
    assert removed.warnings == (_IMAGE,)
    assert "logo" not in removed.html
    assert "<img" not in hostile.html
    assert "javascript" not in hostile.html
    assert hostile.warnings == (_IMAGE,)
    assert kept.html == "<p>See  here</p>\n"
    assert kept.warnings == (_IMAGE,)


def test_code_does_not_warn():
    fmt, _sanitizer = _format()
    source = "`<b>x</b>`\n\n```\n<b>y</b>\n![a](b)\n:::spoiler\n# Title\n```\n"

    result = fmt.render(source)

    assert result.warnings == ()
    assert "<b>" not in result.html
    assert "<img" not in result.html
    assert "<details>" not in result.html
    assert "<h1" not in result.html
    assert "<h2" not in result.html
    assert fmt.headings(source) == ()


def test_details_and_callout():
    fmt, _sanitizer = _format()

    details = fmt.render(":::details More info\nHidden **detail** text.\n:::\n")
    empty_details = fmt.render(":::details\nbody\n:::\n")
    callout = fmt.render(":::callout Heads up\nBack up before migrating.\n:::\n")
    empty_callout = fmt.render(":::callout\nJust a note.\n:::\n")
    titled_kind = fmt.render(":::callout warning Hello\nBody.\n:::\n")

    assert details.warnings == ()
    assert "<details><summary>More info</summary>" in details.html
    assert "<strong>detail</strong>" in details.html
    assert "</details>" in details.html
    assert "<div" not in details.html
    assert "<summary>Details</summary>" in empty_details.html
    assert 'data-component="callout"' in callout.html
    assert 'data-kind="note"' in callout.html
    assert "<strong>Heads up</strong>" in callout.html
    assert "<aside" in callout.html
    assert "<strong>" not in empty_callout.html
    assert "Just a note." in empty_callout.html
    assert 'data-kind="note"' in titled_kind.html
    assert "<strong>warning Hello</strong>" in titled_kind.html


def test_unclosed_directive_ends_at_the_container():
    fmt, _sanitizer = _format()
    source = "> :::details T\n> inside\n\n## After\n"

    result = fmt.render(source)

    assert "<details>" in result.html
    assert "</details>" in result.html
    assert "inside" in result.html
    assert "<h2>After</h2>" in result.html
    assert result.warnings == ()
    assert fmt.headings(source) == (Heading(2, "After", 3),)


def test_other_colon_lines_stay_text_and_warn_once():
    fmt, _sanitizer = _format()

    result = fmt.render(":::spoiler nope\n\n:::also\n\nhello :::fine\n\n::details\n")

    assert ":::spoiler nope" in result.html
    assert ":::also" in result.html
    assert "hello :::fine" in result.html
    assert "::details" in result.html
    assert "<details>" not in result.html
    assert result.warnings == (_DIRECTIVE,)


def test_links_keep_only_allowed_schemes():
    fmt, _sanitizer = _format()
    source = "\n".join([
        "[a](https://example.com)",
        "[b](http://example.com)",
        "[c](mailto:a@b.c)",
        "[d](/docs)",
        "[e](#frag)",
        "[f](javascript:alert(1))",
        "[g](ftp://example.com/a)",
        "[h](data:text/html,hi)",
        "[i](//evil.example)",
        "[docs][id]",
        "",
        "[id]: https://example.com/ref",
        "",
    ])

    result = fmt.render(source)

    assert result.warnings == ()
    assert '<a href="https://example.com">a</a>' in result.html
    assert '<a href="http://example.com">b</a>' in result.html
    assert '<a href="mailto:a@b.c">c</a>' in result.html
    assert '<a href="/docs">d</a>' in result.html
    assert '<a href="#frag">e</a>' in result.html
    assert '<a href="https://example.com/ref">docs</a>' in result.html
    assert 'href="javascript:' not in result.html
    assert "[f](javascript:alert(1))" in result.html
    assert "[g](ftp://example.com/a)" in result.html
    assert "[h](data:text/html,hi)" in result.html
    assert "[i](//evil.example)" in result.html
    bare = fmt.render("https://example.com\n")
    assert "<a " not in bare.html
    assert bare.warnings == ()
    quoted = fmt.render('"quotes" --\n')
    assert "“" not in quoted.html
    assert "--" in quoted.html
    tilde = fmt.render("~nope~\n")
    assert "<s>" not in tilde.html


def test_hostile_fragment_is_inert_and_warns():
    fmt, sanitizer = _format()
    source = "\n".join([
        "## Notes",
        "",
        "<script>alert(1)</script>",
        "",
        "[click me](javascript:alert(1))",
        "",
        "<img src=x onerror=alert(1)>",
        "",
        "![logo](https://evil.example/logo.png)",
        "",
        '<a href="javascript:alert(1)" onclick="steal()">link</a>',
        "",
        "Plain text survives.",
    ])

    result = fmt.render(source)

    assert "<script" not in result.html
    assert "<img" not in result.html
    assert "<a " not in result.html
    assert 'href="' not in result.html
    assert "<p></p>" in result.html
    assert result.warnings == (_HTML, _IMAGE)
    assert sanitizer.calls == [result.html]
    assert_semantic(
        result.html,
        (
            {"h2": "Notes"},
            {"p": "<script>alert(1)</script>"},
            {"p": "[click me](javascript:alert(1))"},
            {"p": "<img src=x onerror=alert(1)>"},
            {"p": '<a href="javascript:alert(1)" onclick="steal()">link</a>'},
            {"p": "Plain text survives."},
        ),
    )


def test_feature_tour_matches_the_reader_blocks():
    fmt, sanitizer = _format()
    publish = MARKDOWN_FEATURE_TOUR.operations[0]
    assert isinstance(publish, Publish)

    result = fmt.render(publish.content)

    assert result.warnings == ()
    assert sanitizer.calls == [result.html]
    assert_semantic(result.html, MARKDOWN_FEATURE_TOUR.blocks)


def test_compilable_garbage_does_not_raise():
    fmt, _sanitizer = _format()

    result = fmt.render("::: \n<\n# \n![ \n")

    assert isinstance(result, type(fmt.render("")))
    assert isinstance(result.warnings, tuple)


def test_headings_examples_from_appendix_c():
    fmt, sanitizer = _format()

    assert fmt.headings("intro\n\n## One *em* `code`\n\ntext\n\n### Two\n") == (
        Heading(2, "One em code", 2),
        Heading(3, "Two", 6),
    )
    assert fmt.headings("Title\n=====\n\nSub\n---\n") == (
        Heading(1, "Title", 0),
        Heading(2, "Sub", 3),
    )
    assert fmt.headings("- ## x\n") == ()
    assert fmt.headings("> ## x\n") == ()
    assert fmt.headings("```\n## Hidden\n```\n") == ()
    assert fmt.headings(":::details Box\n## Inside\n:::\n") == ()
    assert fmt.headings(":::callout Note\n## Inside\n:::\n\n## Shown\n") == (
        Heading(2, "Shown", 4),
    )
    assert fmt.headings("## See [docs](https://example.com)\n") == (
        Heading(2, "See docs", 0),
    )
    assert sanitizer.calls == []


def test_nested_headings_are_not_section_boundaries():
    fmt, _sanitizer = _format()
    source = "\n".join([
        "```",
        "## Hidden",
        "```",
        "",
        "- ## x",
        "",
        "> ## y",
        "",
        "1. ## z",
        "",
        ":::details T",
        "## Inside",
        ":::",
        "",
        "## Outside",
    ])

    assert fmt.headings(source) == (Heading(2, "Outside", 14),)
    rendered = fmt.render("- # Secret\n")
    assert "<h1" not in rendered.html
    assert "<h2>Secret</h2>" in rendered.html
    assert rendered.warnings == (_H1,)
    assert fmt.headings("- # Secret\n") == ()


def test_warnings_follow_the_document_and_do_not_raise():
    fmt, _sanitizer = _format()

    result = fmt.render("# Top\n\n<b>x</b>\n\n![a](https://example.com/a.png)\n\n:::nope\n")

    assert result.warnings == (_H1, _HTML, _IMAGE, _DIRECTIVE)
    try:
        fmt.render(result.html)
    except InvalidContent:
        raise AssertionError("rendered html must stay compilable") from None
