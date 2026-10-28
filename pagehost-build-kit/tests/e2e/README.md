# End-to-end scenarios

Each file in `scenarios/` is **a list of tool calls and the page they must have produced**. Nothing
else. They talk to the system the way an agent does (MCP tools, over HTTP, with a bearer token) and
look at the result the way a reader does (the served page). They know nothing about how the system is
built, so the same files can judge a different implementation (a rewrite in another language, a
different storage engine, a different theme).

```
pytest tests/e2e                         # boots a real server on a free port and runs everything
pytest tests/e2e -k rollback             # pick scenarios by name
python scripts/mutation_check.py         # prove the scenarios fail when the system is broken
```

Against any other deployment (the web server in front of the pages must be reachable):

```
PAGEHOST_E2E_MCP_URL=https://host/mcp/  PAGEHOST_E2E_TOKEN=...  pytest tests/e2e
PAGEHOST_E2E_PAGE_ORIGIN=http://localhost:8080   # optional: reach <id>.pages... via one origin + Host header
```

## Anatomy of a scenario

```yaml
name: append-to-the-end-of-a-page        # must equal the file name after the NN- prefix
status: ready                            # or `planned`: specified, not built; expected to fail (strictly)
description: ...
steps:                                   # the tool calls, in order
  - call: publish_page
    as: page                             # save the result; later steps use ${page.id}, ${page.url}
    args: {title: Release notes, content: "..."}
    expect: {version: 1, url: {matches: "^https?://"}}      # partial match on the tool's result
  - call: replace_text
    args: {id: "${page.id}", old: "x", new: "y"}
    expect_error: {code: edit_conflict, details: {matches: 0}}   # the call must fail like this
final:                                   # the page it must have produced
  page: page
  versions: 2                            # number of versions in the history
  source: |-                             # exact source (trailing whitespace ignored)
    ...
  snapshot:                              # what a reader sees, as data (see below)
    title: Release notes
    blocks: [{h2: v1.0}, {ul: [First release]}]
```

`${unique}` is a per-run token for titles you will search for, so scenarios do not collide on a shared
server. `{gen: repeat|concat, ...}` builds big inputs (see `13-...`). Other final checks: `blocks_include`
(blocks present in this order), `source_contains` / `source_excludes`, `page_text_contains` /
`page_text_excludes`, and `gone: true` (the URL must no longer serve a page).

**Matchers** in `expect`: a plain value must equal; a mapping is a subset match; plus
`{matches: regex}`, `{contains: x}`, `{not_contains: x}`, `{length: n}`, `{min_length: n}`,
`{absent: true}`, `{any: true}`.

**Every served page is also checked to be inert**, in every scenario: no scripts, event handlers,
`javascript:`/`data:` URLs, forms, frames, external images or stylesheets.

## The page snapshot

The extractor reduces the served HTML to the content and documented meaning, ignoring everything that
is a rendering choice (classes, wrappers, whitespace, stylesheets, the footer, how a date is written).

| Block | Meaning |
|---|---|
| `h1`..`h6`, `p` | text, with inline marks written as `**strong**`, `*em*`, `` `code` ``, `~~del~~`, `[text](href)` |
| `ul`, `ol` | item texts (an item with a nested list is `{text, ul|ol}`) |
| `table` | `{head: [...], rows: [[...]]}` |
| `pre`, `blockquote`, `hr` | code text, quote text, `true` |
| `callout` | `{kind, title?, text}` (a bare `<aside>` is a `note`) |
| `details` | `{summary, text, open?}` |
| `toc` / `stats` / `timeline` / `compare` | the components in `docs/semantic-css.md` |

## Rules that keep scenarios implementation-blind (enforced by `test_harness.py`)

* Use only public tools, their arguments, results and error codes, and the served page.
* Never mention storage, files, paths, stylesheets, class names, libraries or languages.
* Page ids are never written down: they come from results (`${page.id}`).
* Assert outcomes, not mechanisms (an inert page, not which layer made it inert).
* The harness (`harness/`) must not import the implementation. Only `conftest.py` may know how to start it.
* Expected pages are written from the intended behaviour, never pasted from whatever the system printed.
