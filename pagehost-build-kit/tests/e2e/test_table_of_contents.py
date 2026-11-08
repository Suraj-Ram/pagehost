"""A published page always serves a table of contents.

The scenario snapshots only read `<main>`. The contents list is in the header, so this
test fetches the served document and checks the outline itself.
"""
from __future__ import annotations

import asyncio

_CONTENT = """\
# Overview

The launch covers two regions.

## Details

Staging is above target.

### More

A closer look.

## Next

Ship the fix.
"""

# `# Overview` is a markdown level-1 heading. The page title is the only h1, so the
# body renders it as h2, and the contents list still nests Details and Next under it.
_CONTENTS = """\
<nav data-component="toc" aria-label="Contents">
<p data-role="label">On this page</p>
<ol>
<li><a href="#overview">Overview</a><ul>
<li><a href="#details">Details</a><ul>
<li><a href="#more">More</a></li>
</ul>
</li>
<li><a href="#next">Next</a></li>
</ul>
</li>
</ol>
</nav>
"""

_BODY = """\
<h2 id="overview">Overview</h2>
<p>The launch covers two regions.</p>
<h2 id="details">Details</h2>
<p>Staging is above target.</p>
<h3 id="more">More</h3>
<p>A closer look.</p>
<h2 id="next">Next</h2>
<p>Ship the fix.</p>
"""


def test_published_page_serves_a_table_of_contents(endpoint):
    async def go():
        async with endpoint.connect() as session:
            page = await session.call(
                "publish_page",
                {"title": "Launch notes", "content": _CONTENT},
            )
        return page, endpoint.fetch(page["url"])

    page, html = asyncio.run(go())

    assert page["version"] == 1
    header, rest = html.split("<main>\n", 1)
    main, _footer = rest.split("\n</main>", 1)
    assert header.count("<h1") == 1
    assert "<h1>Launch notes</h1>" in header
    assert _CONTENTS in header
    assert main == _BODY
    assert "<h1" not in main
    assert 'data-component="toc"' not in main
