"""The matcher keeps content and documented meaning, and drops presentation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from acceptance.cases import SCENARIOS
from acceptance.semantic import semantic_view

ROOT = Path(__file__).resolve().parents[2]
RENDERED = ROOT / "pagehost-build-kit" / "rendered-pages"
REFERENCE_SNAPSHOT = (
    ROOT / "pagehost-build-kit" / "tests" / "e2e" / "harness" / "snapshot.py"
)

STYLED = """
<html>
<head>
  <link rel="stylesheet" href="/_assets/pagehost.css">
  <style>h2 { color: red } .x { font-weight: 700 }</style>
</head>
<body>
  <header><h1 class="title">Team handbook</h1></header>
  <main>
    <div class="wrap">
      <h2 class="x" style="color: red">Welcome</h2>
      <p class="lead">Hello <strong class="y">team</strong></p>
    </div>
  </main>
  <footer class="meta">v1 · updated 2026-10-27 00:00 UTC</footer>
</body>
</html>
"""

PLAIN = "<h2>Welcome</h2><p>Hello <strong>team</strong></p>"


def test_stylesheet_classes_and_shell_are_not_content():
    styled = semantic_view(STYLED)
    plain = semantic_view(PLAIN)

    assert styled.blocks == plain.blocks
    assert styled.title == "Team handbook"
    assert plain.title == ""
    assert styled.blocks == (
        {"h2": "Welcome"},
        {"p": "Hello **team**"},
    )


def test_inline_marks_survive_as_text():
    html = (
        "<p>See <em>how</em> we use <code>code</code>, <del>old</del> words, "
        'and a <a href="https://example.com/docs">link</a>.</p>'
    )

    assert semantic_view(html).blocks == (
        {"p": "See *how* we use `code`, ~~old~~ words, and a [link](https://example.com/docs)."},
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_scenario_matches_the_rendered_reference_page(scenario):
    html = (RENDERED / f"{scenario.name}.html").read_text(encoding="utf-8")
    view = semantic_view(html)

    assert view.title == scenario.title
    assert view.blocks == scenario.blocks


def test_rendered_pages_match_the_build_kit_snapshot(rendered_page: Path):
    html = rendered_page.read_text(encoding="utf-8")
    view = semantic_view(html)
    reference = _reference_snapshot(html)

    assert view.title == reference["title"]
    assert list(view.blocks) == reference["blocks"]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "rendered_page" not in metafunc.fixturenames:
        return
    pages = sorted(path for path in RENDERED.glob("*.html") if path.name != "index.html")
    metafunc.parametrize("rendered_page", pages, ids=[path.stem for path in pages])


def _reference_snapshot(html: str) -> dict:
    spec = importlib.util.spec_from_file_location("pagehost_reference_snapshot", REFERENCE_SNAPSHOT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {REFERENCE_SNAPSHOT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.snapshot(html)
