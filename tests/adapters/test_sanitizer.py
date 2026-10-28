"""Appendix D: hostile fragments come out inert; allowed markup survives."""

from __future__ import annotations

from pagehost.adapters.sanitizer import Nh3Sanitizer
from pagehost.domain.ports import HtmlSanitizer


def _clean(html: str) -> str:
    sanitizer: HtmlSanitizer = Nh3Sanitizer()
    return sanitizer.clean(html)


def test_script_and_style_are_removed_with_their_content():
    cleaned = _clean("<p>before</p><script>alert('xss')</script><style>body{color:red}</style><p>after</p>")

    assert "<script" not in cleaned
    assert "<style" not in cleaned
    assert "alert" not in cleaned
    assert "color:red" not in cleaned
    assert "<p>before</p>" in cleaned
    assert "<p>after</p>" in cleaned


def test_svg_is_dropped_and_does_not_keep_a_handler_or_script():
    cleaned = _clean('<svg onload="alert(1)"><script>alert(2)</script>label</svg>')

    assert "<svg" not in cleaned
    assert "onload" not in cleaned
    assert "alert" not in cleaned
    assert "label" in cleaned


def test_iframe_is_dropped_and_its_text_is_kept():
    cleaned = _clean('<iframe src="https://evil.example/frame">fallback</iframe>')

    assert "<iframe" not in cleaned
    assert "evil.example" not in cleaned
    assert "fallback" in cleaned


def test_event_handlers_and_style_attributes_are_removed():
    cleaned = _clean(
        '<p onclick="alert(1)" onmouseover="steal()" style="color:red" class="x">text</p>'
        '<details ontoggle="alert(2)" open><summary>More</summary></details>'
    )

    assert "onclick" not in cleaned
    assert "onmouseover" not in cleaned
    assert "ontoggle" not in cleaned
    assert "alert" not in cleaned
    assert "style=" not in cleaned
    assert "class=" not in cleaned
    assert "<p>text</p>" in cleaned
    assert "<details" in cleaned
    assert "open" in cleaned
    assert "<summary>More</summary>" in cleaned


def test_javascript_and_data_urls_are_inert():
    javascript = _clean('<a href="javascript:alert(1)">js</a>')
    mixed_case = _clean('<a href="JAVASCRIPT:alert(1)">js</a>')
    data = _clean('<a href="data:text/html,hi">data</a>')

    for cleaned in (javascript, mixed_case, data):
        assert "javascript:" not in cleaned.lower()
        assert "data:" not in cleaned.lower()
        assert "alert" not in cleaned
        assert 'rel="noopener noreferrer"' in cleaned

    assert ">js</a>" in javascript
    assert ">data</a>" in data


def test_comments_are_stripped():
    cleaned = _clean("<!-- secret --><p>visible</p><!--<script>alert(1)</script>-->")

    assert "secret" not in cleaned
    assert "<!--" not in cleaned
    assert "<script" not in cleaned
    assert cleaned == "<p>visible</p>"


def test_links_get_noopener_noreferrer_and_allowed_urls_pass():
    https = _clean('<a href="https://example.com/docs">docs</a>')
    http = _clean('<a href="http://example.com/docs">docs</a>')
    mailto = _clean('<a href="mailto:a@b.example">mail</a>')
    relative = _clean('<a href="/guide">guide</a>')
    fragment = _clean('<a href="#summary">summary</a>')
    replaced = _clean('<a href="https://example.com/" rel="opener">docs</a>')

    for cleaned in (https, http, mailto, relative, fragment, replaced):
        assert 'rel="noopener noreferrer"' in cleaned

    assert 'rel="opener"' not in replaced

    assert 'href="https://example.com/docs"' in https
    assert 'href="http://example.com/docs"' in http
    assert 'href="mailto:a@b.example"' in mailto
    assert 'href="/guide"' in relative
    assert 'href="#summary"' in fragment


def test_a_plain_paragraph_survives():
    assert _clean("<p>hello</p>") == "<p>hello</p>"


def test_an_allowed_data_status_survives_and_unknown_data_attributes_do_not():
    cleaned = _clean('<p data-status="ok" data-evil="1">fine</p>')

    assert cleaned == '<p data-status="ok">fine</p>'
