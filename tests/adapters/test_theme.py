"""The theme wraps a fragment in the §8.1 shell and ships pagehost.css unchanged."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pagehost.adapters.theme import PagehostTheme
from pagehost.domain.models import Document, TocHeading

ROOT = Path(__file__).resolve().parents[2]
BUILD_KIT_CSS = ROOT / "pagehost-build-kit" / "pagehost.css"


def test_static_assets_match_the_build_kit_stylesheet():
    assets = PagehostTheme().static_assets()

    assert list(assets) == ["pagehost.css"]
    assert assets["pagehost.css"] == BUILD_KIT_CSS.read_bytes()


def test_title_is_escaped_in_the_title_and_the_heading():
    title = 'Say "hi" & <b>go</b>'
    html = PagehostTheme().render_document(_document(title=title))
    escaped = "Say &quot;hi&quot; &amp; &lt;b&gt;go&lt;/b&gt;"

    assert f"<title>{escaped}</title>" in html
    assert f"<header><h1>{escaped}</h1>\n" in html
    assert title not in html
    assert html.count("<h1>") == 1


def test_fragment_script_is_not_introduced_by_the_shell():
    fragment = '<p>{title}</p><script>alert(1)</script>'
    themed = PagehostTheme().render_document(_document(body_html=fragment))
    bare = PagehostTheme().render_document(_document(body_html="<p>Hello</p>"))

    before, rest = themed.split("<main>\n", 1)
    main, after = rest.split("\n</main>", 1)

    assert "<script" not in bare.lower()
    assert themed.lower().count("<script") == 1
    assert main == fragment
    assert "<script" not in before.lower()
    assert "<script" not in after.lower()


def test_shell_links_the_stylesheet_without_script_style_or_class():
    html = PagehostTheme().render_document(_document(body_html="<p>Hello</p>"))

    assert html.count('<link rel="stylesheet" href="/_assets/pagehost.css">') == 1
    assert "<script" not in html.lower()
    assert "<style" not in html.lower()
    assert " style=" not in html.lower()
    assert " class=" not in html.lower()
    assert 'class="' not in html.lower()


def test_footer_formats_the_update_time_in_utc():
    eastern = timezone(timedelta(hours=-4))
    html = PagehostTheme().render_document(
        _document(
            version=3,
            updated_at=datetime(2026, 10, 27, 21, 40, tzinfo=eastern),
        )
    )
    naive = PagehostTheme().render_document(
        _document(updated_at=datetime(2026, 10, 27, 16, 55))
    )

    assert "<footer>v3 &middot; updated 2026-10-28 01:40 UTC</footer>" in html
    assert "<footer>v1 &middot; updated 2026-10-27 16:55 UTC</footer>" in naive


def test_fragment_appears_only_inside_main():
    fragment = "<h2>Welcome</h2><p>Only here</p>"
    html = PagehostTheme().render_document(_document(body_html=fragment, title="Handbook"))
    before, rest = html.split("<main>\n", 1)
    main, after = rest.split("\n</main>", 1)

    assert main == fragment
    assert "Only here" not in before
    assert "Only here" not in after
    assert "<h1>Handbook</h1>" in before
    assert "Handbook" not in main


def test_table_of_contents_always_renders_inside_the_header():
    html = PagehostTheme().render_document(_document(body_html="<p>Just text</p>"))
    before, rest = html.split("<main>\n", 1)
    main, _after = rest.split("\n</main>", 1)

    assert '<nav data-component="toc" aria-label="Contents">' in before
    assert '<p data-role="label">On this page</p>' in before
    assert "<ol>\n</ol>" in before
    assert "data-component" not in main
    assert main == "<p>Just text</p>"
    assert " class=" not in html
    assert " style=" not in html.lower()


def test_table_of_contents_nests_by_markdown_level():
    html = PagehostTheme().render_document(
        _document(
            toc=(
                TocHeading("welcome", 2, "Welcome"),
                TocHeading("how", 3, "How"),
                TocHeading("principles", 2, "Principles"),
                TocHeading("deep", 5, "Deep"),
                TocHeading("overview", 1, "Overview"),
                TocHeading("details", 2, "Details"),
                TocHeading("more-less", 3, "More & <b>"),
            )
        )
    )
    toc = html.split("<nav", 1)[1].split("</nav>", 1)[0]

    assert toc == (
        ' data-component="toc" aria-label="Contents">\n'
        '<p data-role="label">On this page</p>\n'
        "<ol>\n"
        '<li><a href="#welcome">Welcome</a><ul>\n'
        '<li><a href="#how">How</a></li>\n'
        "</ul>\n"
        "</li>\n"
        '<li><a href="#principles">Principles</a><ul>\n'
        '<li><a href="#deep">Deep</a></li>\n'
        "</ul>\n"
        "</li>\n"
        '<li><a href="#overview">Overview</a><ul>\n'
        '<li><a href="#details">Details</a><ul>\n'
        '<li><a href="#more-less">More &amp; &lt;b&gt;</a></li>\n'
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</li>\n"
        "</ol>\n"
    )
    assert 'href="#overview"' not in html.split("<main>\n", 1)[1]


def _document(
    *,
    title: str = "Team handbook",
    body_html: str = "<p>Hello</p>",
    version: int = 1,
    updated_at: datetime | None = None,
    toc: tuple[TocHeading, ...] = (),
) -> Document:
    return Document(
        page_id="team-handbook",
        title=title,
        body_html=body_html,
        version=version,
        updated_at=updated_at or datetime(2026, 10, 27, 16, 55, tzinfo=timezone.utc),
        toc=toc,
    )
