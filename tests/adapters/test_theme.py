"""The theme wraps a fragment in the §8.1 shell and ships pagehost.css unchanged."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from pagehost.adapters.theme import PagehostTheme
from pagehost.domain.models import Document

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
    assert f"<header><h1>{escaped}</h1></header>" in html
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


def _document(
    *,
    title: str = "Team handbook",
    body_html: str = "<p>Hello</p>",
    version: int = 1,
    updated_at: datetime | None = None,
) -> Document:
    return Document(
        page_id="team-handbook",
        title=title,
        body_html=body_html,
        version=version,
        updated_at=updated_at or datetime(2026, 10, 27, 16, 55, tzinfo=timezone.utc),
    )
