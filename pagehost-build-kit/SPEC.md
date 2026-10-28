# pagehost: System Specification

**Version 1.0 · Audience: the engineer or agent who will build this system · Status: normative**

pagehost lets an AI agent publish and edit small web pages through a handful of MCP tools. Pages are
authored in a compact Markdown dialect, rendered to semantic HTML, styled by a provided stylesheet, and
served as static files inside a private network.

This document is the single source of truth for *behaviour*. It is deliberately precise about what the
system must do, and silent about how, except where the design depends on it.

---

## 0. How to use this document

### 0.1 What you are given

| Input | What it is | Authority |
|---|---|---|
| **This specification** | Behaviour, contracts, algorithms, security rules | Normative |
| **`pagehost.css`** | The finished stylesheet (about 16 KB). Serve it **unmodified**. Do not write your own CSS | Normative: it defines what markup is styled (§8) |
| **End-to-end scenarios** (`scenarios/*.yaml`, 20 files) | Each is a list of MCP tool calls plus the page they must have produced | **Acceptance tests. They win over any prose here** |
| **Rendered pages** (`rendered-pages.zip`, 17 HTML files + `index.html`) | The real page each scenario produces, served form, stylesheet inlined so it opens standalone | Reference output: *semantic* equivalence required, byte equality not |
| Optionally: `docs/showcase.html`, `contract/openapi.json`, the e2e harness (`tests/e2e/`) | Component showcase, REST contract in machine form, the scenario runner | Reference |

### 0.2 Precedence when sources disagree

1. A `ready` end-to-end scenario that fails is a bug in your implementation. Do not edit scenarios to pass.
2. Otherwise this specification.
3. Otherwise the rendered pages.
4. If something is unspecified, choose the simplest behaviour, record the decision in your README, and do not
   invent new tool parameters, tool names or error codes.

### 0.3 Conventions

**MUST / MUST NOT / SHOULD / SHOULD NOT / MAY** have their RFC 2119 meaning. "Caller" means the agent (or
program) using the MCP tools. "Reader" means a person viewing a served page. Exact wording of human-readable
messages is **not** contractual unless stated; **codes, field names and shapes are**.

### 0.4 The reference stack (a decision, not an accident)

The product owner decided on: **Python 3.11+, FastAPI, FastMCP (standalone `fastmcp` package), markdown-it-py
with `mdit-py-plugins`, `nh3`, SQLite (WAL), uvicorn (single process), nginx**. You SHOULD use it. You MAY
deviate if every `ready` scenario passes and the architectural rules in §2 hold, because a stated goal is that
*the content language, the theme, the storage and the language of the whole platform can each be rewritten
behind stable interfaces*.

---

## 1. Purpose, scope, glossary

### 1.1 Goals

1. **Agent-first and token-lean.** Every token an agent reads or writes costs money and context. The tool
   design (§6) exists to keep both small: the agent writes only *new* text, reads *narrowly*, and gets *tiny*
   results.
2. **Safe by construction.** Content authored by an agent that has read untrusted text must never be able to
   run code in, or exfiltrate data from, a reader's browser (§10).
3. **Semantic content, platform-owned looks.** Authors write meaning (`data-status="blocked"`), never colours.
   One stylesheet owns all presentation (§8).
4. **Rewritable parts.** Content format, theme, storage, publishing target and URL scheme are replaceable
   behind small interfaces (§2).
5. **Versioned and recoverable.** Every change is a new immutable version; nothing is lost; any version can be
   restored (§3).

### 1.2 Non-goals (v1)

Per-user identity or permissions (one shared bearer token), images or other uploaded media, interactive
pages (no JavaScript in served pages), a human editing UI, comments, search, page-level ACLs, version pruning,
restoring a deleted page, multi-instance clustering.

### 1.3 Glossary

| Term | Meaning |
|---|---|
| **Page** | A titled document with an id, a history of versions, and one served URL |
| **Version** | An immutable snapshot: title, format, **source**, author, summary, time. Numbered from 1 |
| **Source** | The text the agent writes (Markdown). The only thing stored durably as content |
| **Fragment** | Sanitized HTML produced from source, with no `<html>`, `<head>` or `<body>` |
| **Document** | A full HTML page: fragment wrapped in the shell (§8.1) and linked to the stylesheet |
| **Section** | A heading plus everything under it up to the next heading of the same or higher level (§5.1) |
| **Section id** | A slug of the heading text, unique within the page; how tools address a section |
| **Outline** | The list of a page's sections with sizes, returned instead of the text for big pages |
| **Warning** | A non-fatal message in a result saying content was altered, removed or unsupported |
| **Inert page** | A page that can run no code and load nothing from elsewhere (§10.3) |

---

## 2. Architecture

### 2.1 Shape

```
 Agent ──MCP (Streamable HTTP, bearer)──┐
 Scripts/ops ──REST (bearer)────────────┤
                                        ▼
                        ┌────────── transports (thin) ──────────┐
                        │  MCP tools          REST        CLI   │
                        └───────────────────┬───────────────────┘
                                            ▼
                               Application service (use cases)
                                            │ only through ports
      ┌───────────────┬───────────────┬─────┴────────┬────────────────┬──────────────┐
      ▼               ▼               ▼              ▼                ▼              ▼
 ContentFormat    HtmlSanitizer      Theme      PageRepository   SitePublisher    UrlScheme
 (Markdown)         (allowlist)    (pagehost)     (SQLite)      (static files)   (template)
                                                       │                │
                                        source of truth: versions   served output
                                                                         │
                                                         web server (nginx), read-only mount
```

### 2.2 Ports (interfaces the application service depends on)

Each port is small. Define them as interfaces/protocols in your language.

| Port | Operations | Contract summary |
|---|---|---|
| **ContentFormat** | `name`; `render(source) → {html, warnings[]}`; `authoring_guide() → text` | `render` is **pure and deterministic**, returns a **sanitized fragment**, raises `invalid_content` only if the input cannot be compiled at all, otherwise returns warnings |
| **SectionedFormat** *(optional capability)* | `headings(source) → [{level, title, line}]` | Top-level headings only, document order, 0-based line index. A format without it simply has no section features (§5) |
| **HtmlSanitizer** | `clean(html) → html` | Allowlist-based (Appendix D). Used by formats |
| **Theme** | `render_document({page_id,title,body_html,version,updated_at}) → html`; `static_assets() → {name: bytes}` | Wraps a fragment into a full document; supplies files the document links |
| **PageRepository** | `create`, `append_version`, `get_version`, `list_versions`, `list_pages`, `mark_deleted` | Durable source of truth; semantics in §3.5 |
| **SitePublisher** | `publish(page_id, version, html)`, `unpublish(page_id)`, `install_assets(assets)` | Makes output visible to the web server. **Idempotent** so a failed publish is repaired by publishing again |
| **UrlScheme** | `url_for(page_id) → url` | e.g. `https://{id}.pages.internal.example.com/` |

### 2.3 Dependency rules (MUST hold; the reference implementation enforces them with a test)

* The **domain** (models, errors, id rules, text/section/edit algorithms, port definitions) depends on the
  language's standard library only.
* The **application service** depends on the domain only.
* **Adapters** (one per port) depend on the domain and third-party libraries, never on transports, the service,
  the composition root, or *each other*.
* **Transports** (MCP, REST, CLI) depend on the domain and the service, never on adapters.
* Exactly **one composition root** names concrete adapters and wires them. Swapping an implementation is a
  one-line change there.

### 2.4 Cross-cutting design decisions

1. **Source of truth vs. derived output.** Versions of *source* are durable. Rendered HTML is derived and
   disposable: deleting all served output and running a re-render MUST restore the site exactly (§9.4).
2. **Each version remembers its format.** A page can hold versions in different content formats. This is the
   migration path to a new content language: re-author with `replace` passing the new format (REST only).
3. **Edit operations are format-agnostic**, working on source *lines* and *text*. Only "where are the
   headings" is format-specific (`SectionedFormat`).
4. **Transports shape, never decide.** Policies such as "a big page reads as an outline" live in the MCP
   transport; the service exposes primitives (read whole, read section, outline).

---

## 3. Domain model and rules

### 3.1 Page and version

| Field | Rule |
|---|---|
| `page_id` | Matches `^[a-z0-9][a-z0-9-]{2,62}$` (starts alphanumeric so it can never equal `_assets` or a temp file; safe as a path segment and a DNS label) |
| `number` | Integer from 1, +1 per version, never reused, **immutable** |
| `title` | Trimmed; 1 to 200 characters; stored per version |
| `format` | Name of the content format used for that version (`markdown`) |
| `source` | UTF-8 text, **LF newlines only** (§3.2), at most `max_source_bytes` (default 1,000,000) |
| `author` | Who made the version (§11) |
| `summary` | Short text about the change; generated by the system (§3.6) unless supplied via REST |
| `created_at` | UTC timestamp of the version. A page's "updated at" is its current version's `created_at` |
| `size_bytes` | UTF-8 byte length of `source` |

### 3.2 Input normalisation (all transports, before anything else)

* `content`, `old`, `new` and every other text a caller supplies have `\r\n` and lone `\r` converted to `\n`.
  Stored sources therefore contain only `\n`. (Parsers' line numbers then agree with line splitting.)
* `title` is trimmed. Empty after trimming, or longer than 200 characters → `invalid_content`.
* After normalisation the UTF-8 size of any resulting source MUST be ≤ `max_source_bytes`, else
  `content_too_large`. This applies to publish, replace, every edit result, and rollback.

### 3.3 Page ids

* Generated by the system, never by the caller: `{slug}-{6 lowercase hex}`.
* `slug(title)`: lowercase; every run of characters outside `[a-z0-9]` becomes `-`; trim leading/trailing `-`;
  truncate to 40 characters then trim `-` again; if empty use `page`.
* If the generated id already exists, generate another; give up after 5 attempts with `page_exists`.
* Any id received from a caller that does not match the id pattern → `invalid_page_id` (checked before any
  lookup or filesystem access, to make path traversal impossible).

### 3.4 Lifecycle

```
publish ──▶ v1 ──edit/append/replace/rollback──▶ v2 ──▶ v3 …
                                  │
                              delete_page ──▶ soft-deleted (history kept, URL stops serving)
```

* A **deleted** page behaves as non-existent to every read or write (`page_not_found`) and is excluded from
  listings. It is not restorable in v1.
* **Rollback never rewinds history.** It appends a *new* version whose title, format and source equal the
  chosen one.
* **Optimistic concurrency.** Every mutation reads the current version, computes the new source, and appends it
  *only if the page is still at that version*; otherwise it fails with `version_conflict` and changes nothing.
  Two concurrent writers MUST NOT silently overwrite each other. (REST callers may also pass `base_version`.)

### 3.5 PageRepository semantics

| Operation | Behaviour |
|---|---|
| `create(page_id, first)` | Stores version 1; `page_exists` if the id is taken (including soft-deleted ids) |
| `append_version(page_id, new, base_version?)` | Atomically adds version `current+1`. `base_version` given and ≠ current → `version_conflict{expected_version, current_version}`. Missing/deleted → `page_not_found` |
| `get_version(page_id, number?)` | `number` omitted = current. `page_not_found` / `version_not_found` |
| `list_versions(page_id)` | Metadata of all versions, oldest first (no source) |
| `list_pages()` | Metadata of the **current** version of each live page, **most recently updated first** (ties broken by id) |
| `mark_deleted(page_id)` | Soft delete; `page_not_found` if absent or already deleted |

All writes MUST be atomic and serialisable (the reference uses SQLite `BEGIN IMMEDIATE`).

### 3.6 Generated history summaries

When the caller does not supply one, the system records: `created`, `append`, `append to {section}`,
`edit text`, `edit text in {section}`, `replace section {section}`, `delete section {section}`,
`full rewrite`, `Rollback to v{N}`. (SHOULD use these strings; no scenario pins them.) The MCP tools never
accept a summary argument (token economy); REST may.

---

## 4. Content format: Markdown (+ two directives)

The only content format in v1 is named `markdown`. A caller writes the **page body**; the platform supplies
the title (the page's only `<h1>`), layout and styling.

### 4.1 Language

* CommonMark, plus **GFM tables** and **strikethrough** (`~~x~~`).
* **Raw HTML is disabled at the parser.** `<b>x</b>` in source is displayed as literal text (and warned about).
  This is the first of two security layers (§10); the sanitizer is the second and MUST NOT be removed because
  the first exists.
* No autolinking, no typographic substitutions.
* **Links**: `http`, `https`, `mailto` schemes, plus relative and fragment (`#id`) links. Any other scheme
  (e.g. `javascript:`) is not turned into a link: the text is shown literally.
* **Images are not supported.** They are removed and a warning is returned.
* **Level-1 headings are demoted to level 2** (the page title is the `<h1>`), with a warning.

### 4.2 Directives

A directive is a fenced block: a line starting with `:::` and a name, the body (any Markdown), and a line
containing only `:::`. An unclosed directive ends at the end of its container. Titles are HTML-escaped.

```
:::details Optional title          →   <details><summary>Optional title</summary>…body…</details>
body                                   (empty title → summary text "Details")
:::

:::callout Optional title          →   <aside><strong>Optional title</strong>…body…</aside>
body                                   (no title → no <strong>)
:::
```

A bare `<aside>` is a **note** callout in the HTML contract (§8.3). Emitting `data-component="callout"
data-kind="note"` on it is allowed and preferred once callout kinds exist (§12).

Any other line that *starts* with `:::` and is not a valid directive is left as text and triggers a warning.

### 4.3 Warning catalogue

Warnings are returned in the `warnings` array of the result and never block the operation. Wording SHOULD be
as below (no scenario pins exact text; scenarios require only that a warning exists where one is due).

| Condition | Message |
|---|---|
| Any level-1 heading | `Level-1 headings were demoted to level 2; the page title is the h1.` |
| Raw HTML tag-like text outside code | `Raw HTML is not supported and is shown as literal text.` |
| Any image | `Images are not supported and were removed.` |
| Paragraph text starting with `:::` that is not a directive | `Found ':::' text that is not a valid directive (supported: details, callout).` |
| `replace_section` content not starting with a heading line | `Replacement does not start with a heading line, so the section's heading was removed. Include the heading line in \`content\`.` |
| An edit whose result equals the current source | `No change: the result is identical to the current version.` |

Code spans and fenced code blocks may contain anything (including HTML) without warning.

### 4.4 The authoring guide

The format supplies a short guide for the agent (verbatim text in Appendix A). It is delivered in the MCP
server instructions (§6.1) and by `GET /api/v1/authoring-guide`. There is **no** MCP tool for it. Keep it
short: it is charged on every request.

### 4.5 `headings(source)`

Return headings in document order as `{level 1..6, title, line}` where `title` is the heading's **plain text**
(inline markup removed; text and code-span content only) and `line` is the 0-based line index of the heading's
first line. Only **top-level** headings count: headings inside code fences, block quotes, lists or directive
bodies are **not** section boundaries (cutting there would break the structure). Setext headings (underlined)
count.

---

## 5. Sections, splicing and edit semantics

These algorithms are format-agnostic and MUST behave as described: the scenarios pin their observable results.

### 5.1 Line model

`lines = source.split("\n")`. A source ending in a newline therefore ends with one empty element. A "blank"
line is empty or whitespace-only.

### 5.2 Sections

From `headings(source)` build one section per heading:

1. **Slug** (the section id base): lowercase the title; replace every run of non-letter/non-digit characters
   (Unicode-aware; underscore counts as a separator) with `-`; trim `-`; if empty, `section`.
2. **Unique ids**: the first heading with a given slug gets it; later ones get `slug-2`, `slug-3`, …,
   re-checking each candidate against ids already issued (so headings *Risks, Risks, Risks 2, Risks* yield
   `risks, risks-2, risks-2-2, risks-3`).
3. **Range**: a section starts at its heading line and ends (exclusive) at the next heading whose level is
   **less than or equal to** its own, else at `len(lines)`. A section therefore **includes its subsections**.
4. Text before the first heading belongs to no section.

Unknown section id → `section_not_found` with `details {section, available[≤50 ids], total_sections}`.

**Section text** (what `read_page(section=…)` returns): `lines[start:end]` with leading and trailing blank lines
removed, joined by `\n`. It includes the heading line.

### 5.3 Splice (how every structural edit is applied)

`splice(lines, start, end, block)` replaces `lines[start:end]` with `block` and normalises the seams:

```
head = lines[:start] with trailing blank lines removed
tail = lines[end:]   with leading AND trailing blank lines removed
out  = head
for part in (block, tail):
    if part is non-empty:
        if out is non-empty: append one blank line
        append part
append "" (one final element, so the source ends with a single "\n")
```

* **Append** is `splice(lines, p, p, block)` with `p = len(lines)` (end of page) or the section's `end` (end of
  that section, i.e. after its subsections, just before the next sibling or higher heading).
* **Replace section** is `splice(lines, start, end, block)`; **delete section** uses an empty `block`.
* `block` is the caller's content as lines with surrounding blank lines removed (internal indentation kept).
  Empty content → `invalid_content`.
* Consequence worth stating: appended content is its **own block** (blank line before it). Appending `- item`
  to an existing list yields a *loose* list. This is a known, accepted limitation (§15).

### 5.4 Operations

| Operation | Algorithm | Notes |
|---|---|---|
| **append(content, section?)** | splice at end-of-page or end-of-section | To add a **new sibling section**, append to the section it should follow with content that starts with the new heading; it becomes addressable at once |
| **replace_section(section, content)** | splice over the section's range | Replaces nested subsections too. If `content`'s first heading is not on its first line, still apply, plus the warning in §4.3 |
| **delete_section(section)** | splice with empty block | Removes subsections too; they stop being addressable |
| **replace_text(old, new, section?)** | exact match (§5.5), optionally restricted to the section's line range | |
| **replace_page(content, title?)** | new source = content; title kept if omitted | |
| **rollback(to_version)** | new version = copy of that version's title/format/source | Always creates a version |

A mutation whose resulting source is **identical** to the current one MUST NOT create a version: return the
current version number, `changed: "+0/-0"`, and the "No change" warning. (Rollback and `replace_page` are exempt.)

### 5.5 Exact-match edits

For each edit, in order, on the text as it stands after the previous edits (restricted to the section's line
range when a section is given):

* `old` empty → `invalid_content`.
* `old` must occur **exactly once** (counting non-overlapping occurrences of the literal string). Otherwise
  fail with `edit_conflict` and **change nothing** (all-or-nothing across a batch).
* Replace the single occurrence with `new` (`new` may be empty to delete).
* Compare literally: no regex, no whitespace normalisation (CRLF in `old`/`new` is normalised first, §3.2).

**`edit_conflict` details** (the contract that lets a caller self-correct without re-reading the page):

```
details = {
  matches:    <number of occurrences found>,
  candidates: [ {line: <1-based, absolute>, snippet: <that line trimmed, ≤100 chars>, section?: <section id>} ×≤3 ],
  edit_index, current_source       ← REST only; the MCP transport drops these two (token economy)
}
```

* **`matches > 1`**: `candidates` = the first 3 occurrences (their lines), in order.
* **`matches == 0`**: `candidates` = the existing lines that most resemble the text:
  * `probe` = the first non-blank line of `old`, trimmed, at most 120 characters; if shorter than 3, no candidates.
  * Scan at most the first **5,000** lines. Skip blank lines and duplicates of an already-scanned trimmed line.
  * Score each line as `matched_characters / len(probe)`, where `matched_characters` is the sum of matching
    blocks of the longest-matching-subsequence comparison between the line (first 400 characters, trimmed)
    and the probe (no junk heuristics). This rewards a line that *contains* most of the probe, which is how
    agents use short anchors.
  * Keep scores ≥ **0.8**; take the best 3 ordered by score descending, then line ascending.
  * Unrelated text MUST produce **no** candidates rather than noise.
  * Performance: a 4,000-line page MUST answer in well under 2 seconds.
* Each candidate's `section` is the **deepest** section containing the line, when the format has sections.
* For a batch (REST), candidates are produced only for the first edit; later edits' line numbers would be stale.

### 5.6 The change summary `changed`

`changed = "+{added}/-{removed}"`, from the **changed region** of old vs. new source: strip trailing newlines
from both, split into lines (an empty text has zero lines), remove the common prefix and common suffix of lines;
`added` = lines left in the new text, `removed` = lines left in the old. Linear time. Scenarios pin only its
shape (`^\+\d+/-\d+$`), but the numbers should be sensible so an agent can detect a runaway edit.

---

## 6. The MCP interface (the contract agents use)

### 6.1 Transport and server identity

* **MCP Streamable HTTP** at `/mcp/` (a redirect from `/mcp` is acceptable). Server name `pagehost`.
* Every request MUST carry `Authorization: Bearer <token>`; otherwise HTTP 401 (§11.2).
* The server **instructions** (sent at connection) are exactly:
  `Publish and edit web pages. Content format: <format name>` + newline + the format's authoring guide +
  newline + the workflow text. Verbatim text in **Appendix A**. Changing the content format MUST change the
  guide with no other edit.
* Tools take JSON arguments and return JSON objects (or an array for `list_versions`). They are synchronous.

### 6.2 The eleven tools

There are exactly eleven, they are **flat** (one tool, one job, simple arguments; chosen over a single
tool taking a list of operations because small models are more reliable choosing a tool name than filling
a union schema). Tool and parameter names are fixed. Description strings are agent-facing text and SHOULD be
used **verbatim** (Appendix B). **Do not add a `get_authoring_guide` tool, a `summary` parameter, a `format`
parameter, or a `base_version` parameter.**

| # | Tool | Parameters (`?` optional) | Success result |
|---|---|---|---|
| 1 | `publish_page` | `title`, `content` | `{id, url, version, warnings?}` |
| 2 | `read_page` | `id`, `section?`, `full?` (bool, default false), `since?` (int) | see §6.4 |
| 3 | `append_page` | `id`, `content`, `section?` | `{version, changed, warnings?}` |
| 4 | `replace_text` | `id`, `old`, `new`, `section?` | `{version, changed, warnings?}` |
| 5 | `replace_section` | `id`, `section`, `content` | `{version, changed, warnings?}` |
| 6 | `delete_section` | `id`, `section` | `{version, changed, warnings?}` |
| 7 | `replace_page` | `id`, `content`, `title?` | `{version, changed, warnings?}` |
| 8 | `list_pages` | `query?`, `limit?` (int, default 20) | `{total, pages:[{id,title,version,url}]}` |
| 9 | `list_versions` | `id`, `limit?` (int, default 10) | `[{version, by, at, summary?}]` |
| 10 | `rollback_page` | `id`, `to_version` | `{version, changed, warnings?}` |
| 11 | `delete_page` | `id` | `{deleted: true}` |

### 6.3 Result conventions (token economy; MUST)

* `warnings` is **omitted when empty**; when present it is an array of strings.
* Edit-type tools (3 to 7, 10) return only `version` and `changed` (+ warnings). They MUST NOT echo the URL,
  the title, or any source. A caller that wants the page asks `read_page`.
* `publish_page` returns the `id` and `url` once; callers keep them.
* No tool returns whitespace padding or fields beyond those listed.

### 6.4 Per-tool behaviour

#### `publish_page(title, content)`
Normalise (§3.2), validate title and size, **render first** (a failure leaves nothing behind), allocate an id
(§3.3), store version 1 (summary `created`), publish the document (§9). Result
`{id, url, version: 1, warnings?}`. Errors: `invalid_content`, `content_too_large`, `page_exists` (very rare).

#### `read_page(id, section?, full?, since?)`
Evaluate in this order:
1. Load the page (`page_not_found` if missing/deleted). If `section` is given, resolve it (`section_not_found`;
   `unsupported_operation` if the format has no sections).
2. If `since` equals the **current page version** → `{version, unchanged: true}` (no source). Checked first,
   even when `section` is given.
3. If `section` → `{version, section, source}` where `source` is the section text (§5.2).
4. If `full` is true, **or** the estimated size of the whole source is ≤ the read threshold → `{version, source}`.
5. Otherwise (a **big page**) → the outline:
   `{version, tokens, outline: ["{id} h{level} ~{N}t", …], hint: "Big page. Re-call with section=<id> or full=true."}`
   where `tokens` = estimate for the whole source and `N` = estimate for that section's text (including
   subsections). If the format has no sections or the page has no headings, return `{version, source}` instead.

Size estimate: `ceil(characters / 4)`. Threshold: **1000 estimated tokens** (configurable, §11.1). The outline
row's id is exactly the string to pass back as `section`. Errors: `page_not_found`, `section_not_found`,
`unsupported_operation`.

#### `append_page(id, content, section?)`
§5.4 append. No read needed. Errors: `page_not_found`, `section_not_found`, `unsupported_operation` (only when
`section` is given on a format without sections), `invalid_content` (empty), `content_too_large`,
`version_conflict`.

#### `replace_text(id, old, new, section?)`
§5.5 on one edit, restricted to `section` if given. Errors: `edit_conflict`, `invalid_content` (`old` empty),
`section_not_found`, `unsupported_operation`, `page_not_found`, `content_too_large`, `version_conflict`.

#### `replace_section(id, section, content)` / `delete_section(id, section)`
§5.4. `content` includes the heading line. Errors as above (`section_not_found` most likely).

#### `replace_page(id, content, title?)`
New source; `title` replaces the title when given, else kept. Always creates a version.

#### `list_pages(query?, limit?)`
Live pages only, most recently updated first. `query` = case-insensitive substring of the title **or** the id.
`total` is the match count **before** `limit`; `limit` below 1 is treated as 1. Entries have exactly
`id, title, version, url`.

#### `list_versions(id, limit?)`
The most recent `limit` versions (minimum 1), **oldest first**. `by` = author, `at` = UTC `YYYY-MM-DD HH:MM`,
`summary` omitted when absent.

#### `rollback_page(id, to_version)`
Appends a copy of version `to_version` (title, format, source) with summary `Rollback to v{N}`.
`version_not_found` if it does not exist.

#### `delete_page(id)`
Soft delete (§3.4) **and** stop serving the URL (§9.3). Result `{deleted: true}`.

### 6.5 Errors

A failed tool call MUST be reported as an MCP **tool error** (`isError: true`) whose single text content is a
compact JSON object:

```json
{"code":"edit_conflict","message":"…human text…","details":{…}}
```

* `code` is from the table in Appendix F and is the contract; `message` is for humans.
* `details` is **omitted** when it would be empty. Within `details`, drop keys whose value is `null` or an
  empty list, and **always drop `current_source` and `edit_index`** (whole-page dumps cost too many tokens).
* Do not wrap or prefix the JSON.

### 6.6 Verified example session

Calls and results below were captured from the reference implementation (ids differ per run).

```
publish_page {"title":"Q4 plan","content":"## Goals\n\n- Ship beta\n\n## Risks\n\n- Vendor delay\n"}
  → {"id":"q4-plan-076760","url":"https://q4-plan-076760.pages.example.com/","version":1}

read_page {"id":"q4-plan-076760"}
  → {"version":1,"source":"## Goals\n\n- Ship beta\n\n## Risks\n\n- Vendor delay\n"}

append_page {"id":"q4-plan-076760","section":"risks","content":"- Staffing gap"}
  → {"version":2,"changed":"+2/-0"}

replace_text {"id":"q4-plan-076760","old":"Ship betta","new":"Ship GA"}            (typo)
  ! {"code":"edit_conflict","message":"edit 0 matched 0 times; old_str must match exactly once",
     "details":{"matches":0,"candidates":[{"line":3,"snippet":"- Ship beta","section":"goals"}]}}

replace_text {"id":"q4-plan-076760","old":"Ship beta","new":"Ship GA"}
  → {"version":3,"changed":"+1/-1"}

read_page {"id":"q4-plan-076760","since":3}
  → {"version":3,"unchanged":true}

read_page {"id":"q4-plan-076760","section":"nope"}
  ! {"code":"section_not_found","message":"no section 'nope'",
     "details":{"section":"nope","available":["goals","risks"],"total_sections":2}}

replace_section {"id":"q4-plan-076760","section":"goals","content":"no heading here"}
  → {"version":4,"changed":"+1/-3","warnings":["Replacement does not start with a heading line, so the section's heading was removed. Include the heading line in `content`."]}

list_versions {"id":"q4-plan-076760","limit":3}
  → [{"version":2,"by":"agent","at":"2026-10-28 00:50","summary":"append to risks"},
     {"version":3,"by":"agent","at":"2026-10-28 00:50","summary":"edit text"},
     {"version":4,"by":"agent","at":"2026-10-28 00:50","summary":"replace section goals"}]

list_pages {"query":"q4"}
  → {"total":1,"pages":[{"id":"q4-plan-076760","title":"Q4 plan","version":4,"url":"https://q4-plan-076760.pages.example.com/"}]}

rollback_page {"id":"q4-plan-076760","to_version":1}     → {"version":5,"changed":"+7/-7"}
delete_page   {"id":"q4-plan-076760"}                    → {"deleted":true}
read_page     {"id":"q4-plan-076760"}                    ! {"code":"page_not_found","message":"page 'q4-plan-076760' not found"}
```

### 6.7 Size budgets (SHOULD; the reference asserts them in a test)

The tool list as sent to a model (names, descriptions, input schemas) SHOULD total under about 9,000
characters (≈740 tokens), and the server instructions under about 2,600 characters (≈350 tokens). Adding
tools, parameters or prose has a standing per-request cost; justify any increase.

---

## 7. The REST interface (second transport)

REST serves scripts, operators and tests. It exposes the **same use cases** and adds what an agent should not
control: batch edits, optimistic-concurrency tokens, content-format selection, authorship, and maintenance.
No scenario exercises REST; implement it after MCP passes, from these tables (`contract/openapi.json`, if
provided, is the machine-readable form and agrees with them).

* Base path `/api/v1`. JSON in, JSON out. Bearer token required (§11.2).
* Optional header `X-Pagehost-Author` (default `agent`) is recorded as the version's author.
* Success bodies below; errors use the envelope `{"error":{"code","message","details"}}` with `details`
  always an object, and **REST keeps `current_source` and `edit_index`** in `edit_conflict` details.

| Method and path | Request | Success |
|---|---|---|
| `GET /authoring-guide?format=` | | 200 `{format, guide}` |
| `POST /pages` | `{title, content, summary?, format?}` | 201 `PublishOut` |
| `GET /pages?q=&limit=` | | 200 `[PageSummary]` (filtered, cut to `limit`) |
| `GET /pages/{id}?version=&section=` | | 200 `Page` (whole source, or just the section) |
| `PUT /pages/{id}` | `{content, title?, summary?, base_version?, format?}` | 200 `PublishOut` (`format` = migration path) |
| `PATCH /pages/{id}` | `{edits:[{old_str,new_str}]≥1, section?, summary?, base_version?}` | 200 `PublishOut` (batch, all-or-nothing) |
| `GET /pages/{id}/outline?version=` | | 200 `[{id, level, title, chars}]` |
| `POST /pages/{id}/append` | `{content, section?, summary?, base_version?}` | 200 `PublishOut` |
| `PUT /pages/{id}/sections/{section}` | `{content, summary?, base_version?}` | 200 `PublishOut` |
| `DELETE /pages/{id}/sections/{section}?base_version=` | | 200 `PublishOut` |
| `GET /pages/{id}/versions?limit=` | | 200 `[Version]` oldest first; with `limit`, the most recent N |
| `POST /pages/{id}/rollback` | `{to_version ≥ 1}` | 200 `PublishOut` |
| `DELETE /pages/{id}` | | 204 |
| `POST /admin/rerender` | | 200 `{ok: int, failed: {id: message}}` (§9.4) |
| `GET /healthz` | *(no auth)* | 200 `{"status":"ok"}` |

Shapes: `PublishOut {id, url, version, warnings[], lines_added, lines_removed}` ·
`Page {id, title, format, version, url, updated_at, source, section?}` ·
`PageSummary {id, title, version, url, updated_at}` ·
`Version {number, title, format, author, summary, created_at, size_bytes}`.
Timestamps are ISO-8601 UTC. `warnings` is always present (possibly empty) on REST.

Status mapping: `page_not_found`, `version_not_found`, `section_not_found` → 404 · `page_exists`,
`version_conflict`, `edit_conflict` → 409 · `invalid_content`, `invalid_page_id`, `unknown_format`,
`unsupported_operation` → 422 · `content_too_large` → 413 · `unauthorized` → 401 · anything else → 500.
Framework-level request validation errors (malformed JSON, wrong types) may use the framework's own 422 shape.

---

## 8. Rendering, theme and the HTML contract

### 8.1 The page shell (the Theme's output)

The theme wraps the sanitized fragment in this document. The structure is normative; whitespace is not.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<link rel="stylesheet" href="/_assets/pagehost.css">
</head>
<body>
<header><h1>{title}</h1></header>
<main>
{fragment}
</main>
<footer>v{version} &middot; updated {YYYY-MM-DD HH:MM UTC}</footer>
</body>
</html>
```

* `{title}` is **HTML-escaped** in both places.
* The fragment appears **only** inside `<main>`. The page title is the only `<h1>` (§4.1 demotes author h1s).
* The stylesheet is referenced by **path** (`/_assets/pagehost.css`), never inlined, never from another origin
  (the page CSP forbids it, §9.5). No `<script>`, no inline `style` attribute, no `class` attributes anywhere.
* A served page contains **no JavaScript of any kind**.

### 8.2 The stylesheet

`pagehost.css` is provided and is part of the product. You MUST serve it **byte-for-byte unmodified** at
`/_assets/pagehost.css`, and MUST NOT add other stylesheets or style attributes. Its properties (for your
awareness): classless; driven by `--ph-*` tokens; light/dark by OS preference, forceable with
`<html data-theme="dark|light">`; no `url()`, no web fonts, no images; responsive (checked at desktop and a 375px
phone width); print rules; focus rings; text and marker contrast checked in both modes. It styles base elements with no markup at all: `header>h1`, `main`,
`footer`, `h1`–`h6`, `p`, lists, `a`, `strong/em/small/mark/del/kbd/code`, `pre`, `blockquote`, `hr`, `table` (+
`caption`), `details/summary`, `dl`, `figure`.

The `Theme` port installs the stylesheet via `static_assets()` at startup (`install_assets`, §9.2).

### 8.3 The component HTML contract

Meaning is carried by **`data-*` attributes**; the stylesheet decides what they look like. Anything that emits
HTML (a directive renderer, another content format) MUST produce exactly these shapes. The sanitizer allowlist
(Appendix D) already permits every tag and attribute used here.

**Status vocabulary** (stats, timelines, inline badges). The value carries the meaning; the badge text is shown
too, and each value has its own marker shape, so meaning never depends on colour alone.

| `data-status` | Meaning | Badge text |
|---|---|---|
| `done` | Complete | Done |
| `active` | In progress | Active |
| `at-risk` | Needs attention | At risk |
| `blocked` | Cannot proceed | Blocked |
| `planned` | Not started (the default when none is given) | Planned |

A badge is `<span data-role="status">Done</span>` placed inside, or carrying, a `data-status`.

**Callout** (kinds `note` default, `warning`, `success`, `danger`; a bare `<aside>` is a note)
```html
<aside data-component="callout" data-kind="warning"><strong>Title</strong><p>Body.</p></aside>
```

**Table of contents** (headings must carry matching `id`s, §12)
```html
<nav data-component="toc" aria-label="Contents"><p data-role="label">On this page</p>
<ol><li><a href="#summary">Summary</a></li></ol></nav>
```

**Stats** (the status is explicit: a delta's direction does not say whether it is good)
```html
<dl data-component="stats">
  <div data-status="done"><dt>Revenue</dt><dd data-role="value">$5.2M</dd>
  <dd data-role="delta">+12%</dd><dd data-role="status">Done</dd></div>
</dl>
```

**Timeline**
```html
<ol data-component="timeline">
  <li data-status="active"><time datetime="2026-11-15">Nov 15, 2026</time>
  <strong>General availability</strong><span data-role="status">Active</span></li>
</ol>
```

**Compare** (`data-recommended` on at most one article)
```html
<div data-component="compare">
  <article data-recommended>
    <h3>Blue/green cutover<span data-role="flag">Recommended</span></h3><p>Subtitle</p>
    <ul data-role="pros" aria-label="Pros"><li>Instant rollback</li></ul>
    <ul data-role="cons" aria-label="Cons"><li>More coordination</li></ul>
  </article>
</div>
```

**Tables**: plain `<table>` with `<thead>`/`<tbody>`; numeric columns add `data-align="end"` on each `th`/`td`
(also `center`). **Details**: plain `<details>` / `<summary>` (`open` attribute optional).

The MCP-visible Markdown can currently produce only **callout (note)** and **details** from this list. The rest
is the §12 increment; their CSS and contract exist now.

---

## 9. Publishing and serving

### 9.1 Write path (every mutation follows this order)

1. Normalise inputs (§3.2) and compute the new source.
2. **Render** with the version's format → fragment + warnings. If this fails, **nothing** is stored.
3. **Persist** the new version (atomic; conflict-guarded, §3.4).
4. Build the document with the theme (§8.1) and **publish** it (§9.2).
5. Return the tool result.

Step 4 happens after step 3, so a crash between them leaves the **version saved but the old page still served**.
That is recoverable by `rerender` (§9.4) and MUST NOT corrupt anything. Publishing is idempotent.

### 9.2 Served layout and atomic publishing (reference layout)

```
<sites>/_assets/pagehost.css          shared, installed at startup
<sites>/<id>/v<N>/index.html          one directory per version of the rendered document
<sites>/<id>/current  ->  v<N>        a pointer, swapped atomically
```

* Write `index.html` via a temp file + rename. Switch `current` by creating a temp symlink and **renaming it
  over** `current`: a reader sees the old page or the new page, never a missing or partial one.
* `unpublish(id)` removes `current` only (history stays on disk). The URL then answers **404**.
* Asset names must not contain path separators or start with `.`. Ids are validated (§3.3) before any path use.
* The web server mounts `<sites>` **read-only**; only the application writes.

> **If you also use the provided end-to-end harness locally**, its stand-in for the web server reads
> `<sites>/<id>/current/index.html` and expects page URLs whose first DNS label is the id. Keep this layout, or
> run the scenarios in *remote* mode against a real web server (§13.2). Nothing else about storage is observable.

### 9.3 URLs

`UrlScheme.url_for(id)` substitutes `{id}` in a template (`PAGEHOST_URL_TEMPLATE`). Two supported shapes:
**subdomain per page** (`https://{id}.pages.internal.example.com/`, strongest origin isolation, preferred)
and path based (`https://pages.example.com/p/{id}/`). Every tool result that carries a URL uses it.

### 9.4 Re-rendering

`rerender` rebuilds **every live page** from stored sources with the current format and theme, and re-installs
assets. It returns `{ok, failed:{id: message}}`; one page failing MUST NOT stop the others. Required after a
theme or format change, and to repair §9.1. Acceptance: delete everything under `<sites>`, run `rerender`, and
the site is identical in content to before. Exposed as REST `POST /admin/rerender` and CLI `rerender`.

### 9.5 Web server (nginx reference, Appendix E)

* **Per-page origin**: a wildcard `server_name` captures the id from the host and serves
  `<sites>/<id>/current/` with `try_files $uri $uri/ =404`. `/_assets/` is aliased to `<sites>/_assets/`.
* **Response headers on every page and asset** (this is a security control, §10):

```
Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
```

  There is deliberately **no `script-src`**: with `default-src 'none'` the browser refuses all scripts even if a
  sanitizer bug let one through.
* The API/MCP host is a separate `server` (exact name wins over the wildcard) proxying to the app with
  `proxy_buffering off` (Streamable HTTP/SSE), a long read timeout, a body limit (~2 MB) and request rate
  limiting.
* Restrict both to the private network (`allow`/`deny`, VPN, or SSO proxy). Terminate TLS with your internal CA.
* SHOULD (not in the reference config): `Cache-Control: no-cache` on pages so an edit is visible immediately;
  long caching only on `/_assets/`.

---

## 10. Security

### 10.1 Threat model

An agent may have read **untrusted text** (web pages, emails, documents) and then publish content derived from
it, so treat all page source as hostile. The goal is that no such content can run code in a reader's browser,
load a resource from elsewhere, or reach other internal systems from a served page.

### 10.2 Defence in depth (all layers are required; none may be dropped because another exists)

1. **Parser**: raw HTML disabled; non-allowlisted URL schemes not linked (§4.1).
2. **Sanitizer**: allowlist of tags, attributes and URL schemes (Appendix D) applied to every fragment; links
   get `rel="noopener noreferrer"`; comments stripped. Attribute and tag lists are *closed*: the `data-*`
   hooks are an explicit list, never a wildcard.
3. **CSP**: no `script-src`, no external styles/images/fonts/frames/forms (§9.5).
4. **Origin isolation**: one origin per page (subdomain), no cookies shared with any other internal app.
5. **Read-only mount**: the web server cannot modify content.
6. **Authentication** on every write path (§11.2) and the network restriction in §9.5.

### 10.3 The "inert page" invariant

Every served page MUST be inert: no `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>`, `<svg>`, `<math>`,
`<form>`, `<input>`, `<button>`, `<textarea>`, `<select>`, `<video>`, `<audio>`, `<base>`; no `on*` attribute; no
`style` attribute; no `href/src/action/formaction/data/poster/srcset` value beginning `javascript:`, `vbscript:`
or `data:`; `<link>` only as a same-origin stylesheet; `<img>` only with a relative `src` (v1 has no images);
no `meta http-equiv="refresh"`. Escaped markup shown *as text* (`&lt;script&gt;`) is not a violation. The
end-to-end harness checks this on **every** page of **every** scenario.

### 10.4 Other controls

* Constant-time bearer comparison. Never log the token or page source at INFO.
* Size limits (§3.2) bound memory; the near-miss search is bounded (§5.5).
* Soft delete keeps history for audit; every version records its author (§11.3).
* Do not add features that let content reach out (fetching URLs, embedding remote media) without a new threat
  review.

---

## 11. Configuration, authentication, operations

### 11.1 Configuration (environment variables; fail fast on invalid values)

| Variable | Default | Meaning |
|---|---|---|
| `PAGEHOST_TOKEN` | *(required)* | Shared bearer token. **Refuse to start without it** |
| `PAGEHOST_DATA_DIR` | `./data` | Holds the database |
| `PAGEHOST_SITES_DIR` | `<data>/sites` | Served output root |
| `PAGEHOST_URL_TEMPLATE` | `https://{id}.pages.internal.example.com/` | Must contain `{id}` |
| `PAGEHOST_DEFAULT_FORMAT` | `markdown` | Must name a registered format |
| `PAGEHOST_THEME` | `pagehost` | Must name a registered theme (only `pagehost` is required) |
| `PAGEHOST_MAX_SOURCE_BYTES` | `1000000` | §3.2 |
| `PAGEHOST_MCP_AUTHOR` | `agent` | Author recorded for MCP edits |
| `PAGEHOST_MCP_FULL_READ_TOKENS` | `1000` | Read-threshold (§6.4) |

### 11.2 Authentication

* One shared bearer token protects **`/mcp` and everything under `/api/`**; `/healthz` is open.
* Failure: HTTP **401**, header `WWW-Authenticate: Bearer`, body
  `{"error":{"code":"unauthorized","message":"missing or invalid bearer token","details":{}}}`.
* Apply it as middleware over the whole application so the mounted MCP app is covered by the same check.

### 11.3 Attribution

MCP edits record `PAGEHOST_MCP_AUTHOR`; REST edits record `X-Pagehost-Author`. The history (`list_versions`)
therefore shows which caller changed what.

### 11.4 Command line

`serve [--host 0.0.0.0] [--port 8080]` (single process) · `rerender` (exit non-zero if any page failed) ·
`install-assets` · `export-openapi [--out file]` (writes the REST contract).

### 11.5 Operations

* Back up the **database**; the served output is rebuildable.
* One API process is sufficient and simplest; storage writes are serialisable regardless.
* Ship: a container image for the app, a compose file with the app + nginx (sites volume read-write for the app,
  **read-only** for nginx), and the nginx configuration. Include a README with run, test and configuration
  instructions.

---

## 12. Next increment: the planned components

Everything in §8.3 has finished CSS and a fixed HTML shape. What is **not** built is the Markdown side:
directives that produce them. Scenario 19 (`status: planned`) is the executable target; it is expected to
**fail** until this is built, then flipped to `ready`. Parts marked **[pinned]** are fixed by scenario 19;
parts marked **[proposal]** are the product owner's intended design and may be refined, but do not invent
alternatives silently.

### 12.1 Heading ids **[pinned, via the toc]**

Every heading in a rendered fragment MUST carry `id="{section id}"`, computed with exactly the §5.2 slug and
uniqueness rules, so an in-page link `#risks` and the tool argument `section: "risks"` name the same thing.
(Today headings have no ids.) `id` is already allowed by the sanitizer.

### 12.2 Directive syntax

All use the §4.2 fence (`:::name …` / `:::`).

| Directive | Body | Output (§8.3) |
|---|---|---|
| `:::callout [kind] [title]` **[pinned]** | Markdown | Callout. The first word after `callout` is the **kind** iff it is exactly `note`, `warning`, `success` or `danger`; the rest is the title. (A title that begins with a kind word must therefore name the kind explicitly: `:::callout note Warning signs`.) |
| `:::toc` **[pinned]** | **empty**, but still closed: `:::toc` newline `:::` (a bare unclosed `:::toc` would swallow the rest of the page) | Table of contents of the page's **level-2 headings**, in order, as links `#id`; label text `On this page` |
| `:::stats` **[pinned]** | one metric per line: `label \| value \| delta \| status` | Stats. `label`, `value` required; `delta` and `status` optional (leave `delta` empty as `a \| b \| \| done`); `status` ∈ the §8.3 vocabulary |
| `:::timeline` **[pinned]** | one milestone per line: `date \| title \| status` | Timeline. `date` that is ISO `YYYY-MM-DD` becomes `<time datetime="…">` with a human-readable text of your choice (e.g. `Nov 15, 2026`); any other date text is placed in `<time>` with no `datetime`. `status` optional |
| `:::table` **[pinned]** | CSV; first line is the header; RFC 4180 quoting; cells trimmed | A plain table with `<thead>`/`<tbody>`. A column whose non-empty body cells are all numbers (optional sign, currency symbol, thousands commas, decimals, trailing `%`) gets `data-align="end"` on every cell of the column [proposal] |
| `:::compare` | **undefined: do not implement yet** | Reserved. CSS and HTML shape exist (§8.3); the line syntax is an open decision (§15.2) |

### 12.3 Degrading gracefully (MUST)

A malformed or unrecognised line never blocks publishing and never throws. It is rendered as an ordinary
paragraph of the original text and a warning is added, e.g. `stats row 2 needs "label | value"; shown as plain
text` or `timeline row 1: unknown status 'wip'; use done|active|at-risk|blocked|planned` (an unknown status is
treated as absent). A `:::toc` on a page with no level-2 headings renders nothing and warns.

### 12.4 Done when

Scenario 19 passes and is flipped to `ready`; scenario 18 (which has a plain callout and details) still passes;
the showcase fragment (`docs/showcase-fragment.html`, if provided) still survives the sanitizer unchanged.

---

## 13. Acceptance

### 13.1 What "correct" means

The system is correct when **every `ready` end-to-end scenario passes** against a real running instance, and
the scenario marked `planned` is either still failing (before §12) or passing (after). The scenarios are
deliberately **implementation-blind**: they use only the public tools, their arguments, results and error
codes, and the page as a browser would receive it. They never mention storage, paths, stylesheets, class names
or libraries, and ids are never written down (they flow from results).

Each scenario is a list of tool calls and the page they must have produced:

* **steps**: a tool call, optional `expect` (partial match on the result), optional `expect_error`
  (the call must fail with that code/details), optional `as: name` to save the result for `${name.id}`.
* **final**: what the page must be at the end: the exact **source**, the number of **versions**, and a
  **semantic snapshot** of the served page (headings, text with inline marks, lists, tables, callouts,
  details, …) that ignores every rendering choice (wrappers, whitespace, classes, stylesheet, footer, date
  formatting). Every served page must additionally be **inert** (§10.3).

Appendix G lists the 20 scenarios and what each pins; Appendix H specifies the file format, matchers and the
snapshot extraction rules precisely enough to **re-implement a runner** if the harness is not supplied.

### 13.2 Running them

* **Remote mode (works for any implementation).** Start your server and its web server, then run the harness
  with `PAGEHOST_E2E_MCP_URL=https://host/mcp/`, `PAGEHOST_E2E_TOKEN=…`, and, if the page hostnames are not
  resolvable from the test machine, `PAGEHOST_E2E_PAGE_ORIGIN=http://localhost:8080` (requests go there with
  the page's `Host` header).
* **Local default mode** boots the app on a free port and fetches pages by reading the served directory. That
  boot code (`tests/e2e/conftest.py`) is the **only** implementation-aware file; adapt it to your entry point.
  The local fetcher requires the §9.2 layout and page URLs whose first DNS label is the page id
  (e.g. `http://{id}.pages.e2e.test/`).
* Scenarios are independent and share one server; titles that are searched for use a per-run `${unique}` token
  so they never collide.
* Local-run assumption in scenario 13: the read threshold is the default (1000 tokens) or at most a few
  thousand; the generated page is about 5,600 estimated tokens.

### 13.3 The rendered pages (HTML artifacts)

`rendered-pages.zip` contains, for each scenario with a page to show, the page exactly as the reference system
served it (stylesheet inlined so it opens alone), plus `index.html` listing every scenario with its tool calls.
Use them to **look** at the expected result and to compare structure. Equality is **semantic** (the snapshot),
not byte-for-byte: timestamps, ids and whitespace differ per run. In production the stylesheet is linked, not
inlined.

### 13.4 Tests you should write yourself (SHOULD)

These caught real bugs in the reference build; they are cheap and they keep the architecture honest.

| Test | Purpose |
|---|---|
| **Architecture test** | Parses imports and fails if §2.3 is violated |
| **Port contract suites** | One reusable suite per port, run against every implementation including an in-memory fake. Format suite: deterministic, empty source ok, hostile inputs (script tags, `javascript:` URLs, event handlers, SVG, iframes, `data:` links, a `<details ontoggle=…>` attack) yield an inert fragment, never emits `<h1>`. Repository suite: create/duplicate, append + stale `base_version`, missing page/version, ordering, soft delete |
| **Service tests on fakes** | No disk, no network: every use case, id-collision retry, failed-publish-then-rerender repair, format migration, optional-capability behaviour |
| **Algorithm vectors** | Appendix C verbatim |
| **MCP tests** | Exact tool set, schema-size guard (§6.7), compact results, structured compact errors, auth |
| **Stylesheet tests** | Tokens identical in the two dark blocks; text and marker contrast ≥ 4.5:1 / 3:1 in both modes; no `url()`; only attributes the sanitizer allows; the showcase fragment survives the sanitizer unchanged |
| **Mutation check** | Inject a dozen realistic bugs (append at start, delete forgets to unpublish, scope ignored, …) one at a time; each must be caught by the scenario meant to catch it. Breaking only *one* security layer is correctly invisible (the other keeps the page inert); break both to prove the scenario fails |

---

## 14. Build plan and definition of done

### 14.1 Suggested order (each step ends green)

| # | Milestone | Exit criterion |
|---|---|---|
| 1 | **Domain**: ids, errors, models, text helpers, section building, exact-match edits + candidates, port interfaces | Appendix C vectors pass; architecture test passes |
| 2 | **Markdown format + sanitizer** | Format contract suite incl. hostile inputs; `headings()` examples |
| 3 | **Repository, publisher, theme, URL scheme** | Repository contract suite; publish→file layout; atomic swap; assets installed |
| 4 | **Application service** | Service tests on fakes |
| 5 | **MCP transport + auth + composition root** | **Scenarios 01–18 and 20 pass**; schema-size guard; mutation check |
| 6 | **REST, CLI, rerender, deployment (compose + nginx)** | Delete the sites directory → `rerender` restores it; nginx serves pages with the §9.5 headers |
| 7 | **Components (§12)** | Scenario 19 passes and is flipped to `ready` |

### 14.2 Definition of done

- [ ] All `ready` scenarios pass in local **and** remote mode; scenario 19 passes after §12.
- [ ] Exactly the 11 tools, with the parameters and result shapes of §6; no extra tool/parameter/code.
- [ ] Server instructions equal Appendix A; tool descriptions equal Appendix B (verbatim).
- [ ] `pagehost.css` served unmodified; pages have the §8.1 shell; **no script, no inline style, no class** on any served page.
- [ ] Both security layers (parser + sanitizer) present and independently tested; CSP headers as §9.5.
- [ ] Deleting served output + `rerender` restores the site; a failed publish is repaired the same way.
- [ ] Concurrent writers never silently overwrite (`version_conflict`).
- [ ] Architecture test passes; one composition root.
- [ ] README: how to run, test, configure; the decisions you made where this spec was silent.

---

## 15. Known limitations and open decisions

### 15.1 Accepted behaviours (locked by scenarios; do not "fix" without changing the scenarios)

* `replace_section` and `delete_section` act on **nested subsections too**.
* `append_page(section=…)` places content at the end of the section **after its subsections**.
* Appended content is its own block, so appending `- item` to a list makes a loose list (use `replace_text`
  on the last item to extend a list tightly).
* A section replacement without a heading applies, with a warning, leaving the section heading removed.
* The outline's token numbers are an estimate (`ceil(chars/4)`), not a tokenizer count.

### 15.2 Open decisions (ask the product owner; do not decide silently)

1. **`:::compare` line syntax** and how the recommended option is marked.
2. **A one-line `:::toc`** (a leaf directive) instead of the open/close pair, once the directive plugin allows it.
3. **Callout kind syntax**: §12.2 is a proposal ("first word is the kind").
4. **Per-user identity / roles** (today one shared token; an agent can also call REST admin routes).
5. **Images / media**, **version pruning**, **restoring deleted pages**, **tabs and charts** (the latter would
   need a trusted-output path past the sanitizer and a security review).

### 15.3 Stylesheet note (for the stylesheet's owner, not the builder)

`pagehost.css` uses font weights 400 and 500 only. On systems whose UI font has no medium weight, `500` falls
back to `400`, so `<strong>` text can look identical to body text. A one-line remedy (`strong, b { font-weight:
600 }`) was proposed and **deliberately not applied**. Do not change the stylesheet; report it.

### 15.4 Unverified in the reference build

The nginx configuration and compose stack were written but not exercised end to end; the stylesheet was
verified in headless Chromium (desktop, phone, dark, theme overrides), not in Safari or Firefox. Treat both as
things to verify in your environment.


---

## Appendix A: Server instructions (verbatim)

Sent to the agent when it connects. Line 1 is `Publish and edit web pages. Content format: ` + the format name. The next lines are the format's authoring guide, then the workflow text. With the `markdown` format the complete text is:

```text
Publish and edit web pages. Content format: markdown
Write the page body in Markdown. The platform adds the title (the only h1), layout and styling.
- Start headings at `##`. Headings define sections, which tools address by id (slug of the title).
- Supported: lists, tables, quotes, code, bold/italic/~~strike~~, links (http, https, mailto).
- Collapsible: a line `:::details Title`, body, then a line `:::`. Note box: `:::callout Title` ... `:::`.
- Not supported (removed or shown as text, with a warning): raw HTML, images, scripts, styles, forms.

Tools
- New content: append_page (no read needed). Pass section=<id> to add inside a section; to add
  a new sibling section, append to the section it follows with content starting at its heading.
- One phrase: replace_text with a short unique `old`; pass section to make short anchors unique.
- Rewrite a block: read_page(section=<id>), then replace_section (content includes the heading line).
- Remove a block: delete_section. Rewrite everything: replace_page.
- read_page on a big page returns an outline (section ids, sizes): fetch just what you need.
  Pass since=<version> to skip re-reading an unchanged page.
- Edit results give only the new version and "changed" line counts; don't re-read to verify.
- Errors list `candidates` (where `old` occurs, or the closest lines): fix and retry. Warnings mean
  something was altered or removed.
```


## Appendix B: Tool descriptions and input schemas (verbatim)

Use these description strings exactly (they are agent-facing and tuned for brevity). `?` marks an optional parameter; defaults are shown.

| Tool | Parameters | Description |
|---|---|---|
| `publish_page` | `title: string, content: string` | Create a page. `title` is the heading; `content` is the body. Returns id and url. |
| `read_page` | `id: string, section?: string, full?: boolean = false, since?: integer` | Read a page. Big pages return an outline; use `section` (id) for one section or `full` for everything. `since` = last seen version: unchanged pages return no source. |
| `append_page` | `id: string, content: string, section?: string` | Add content at the end of the page, or at the end of section `section`. No read needed. |
| `replace_text` | `id: string, old: string, new: string, section?: string` | Replace one exact text. `old` must occur exactly once (in `section` if given). |
| `replace_section` | `id: string, section: string, content: string` | Replace a whole section with `content` (include its heading line). Don't quote the old text. |
| `delete_section` | `id: string, section: string` | Delete a section, including its subsections. |
| `replace_page` | `id: string, content: string, title?: string` | Rewrite the whole page body (and optionally the title). Prefer the targeted tools. |
| `list_pages` | `query?: string, limit?: integer = 20` | List pages (newest first), optionally filtered by a title/id substring. |
| `list_versions` | `id: string, limit?: integer = 10` | Most recent versions of a page (oldest first). |
| `rollback_page` | `id: string, to_version: integer` | Restore an earlier version as a new version. |
| `delete_page` | `id: string` | Unpublish a page (history is kept). |


## Appendix C: Algorithm test vectors (verified against the reference implementation)

Use these as unit tests for §5. Lines are written as the strings they join to.

**Splice** — source lines `["## A","","a","","## B","","b",""]` (that is `"## A\n\na\n\n## B\n\nb\n"`; sections `A`=lines 0–4, `B`=4–8):

| Call `splice(lines, start, end, block)` | Result |
|---|---|
| `(0, 4, ["## A","","new"])` | `"## A\n\nnew\n\n## B\n\nb\n"` |
| `(4, 8, ["## B","","new"])` | `"## A\n\na\n\n## B\n\nnew\n"` |
| `(8, 8, ["## C"])` *(append at end)* | `"## A\n\na\n\n## B\n\nb\n\n## C\n"` |
| `(4, 4, ["## X"])` *(insert before B)* | `"## A\n\na\n\n## X\n\n## B\n\nb\n"` |
| `(0, 4, [])` *(delete A)* | `"## B\n\nb\n"` |
| `(4, 8, [])` *(delete B)* | `"## A\n\na\n"` |
| `splice(["## A",""], 0, 2, [])` | `""` |
| `splice([""], 1, 1, ["hello"])` *(into an empty page)* | `"hello\n"` |

**Change summary** `line_delta(old, new) → (added, removed)`: `("a\nb\nc","a\nX\nY\nc") → (2,1)` ·
`("same","same") → (0,0)` · `("", "x\ny\n") → (2,0)` · `("a\nb\n","a\n") → (0,1)`.

**Section ranges** — headings `[(2,A,0),(3,A1,3),(3,A2,6),(2,B,9)]`, 12 lines: `a=(0,9) a1=(3,6) a2=(6,9) b=(9,12)`.
Headings `[(3,Deep,0),(2,Shallow,4)]`, 8 lines: `deep=(0,4) shallow=(4,8)`.

**Slugs** — `"Q4 Roadmap & Risks!" → q4-roadmap-risks` · `"***" → section` · `"Überblick" → überblick`.
Titles *Risks, Risks, Risks 2, Risks* → ids `risks, risks-2, risks-2-2, risks-3`.

**`headings()`** —
`"intro\n\n## One *em* `code`\n\ntext\n\n### Two\n"` → `[(2,"One em code",2),(3,"Two",6)]` ·
`"Title\n=====\n\nSub\n---\n"` → `[(1,"Title",0),(2,"Sub",3)]` ·
headings inside a code fence, a list item (`- ## x`), a block quote (`> ## x`) or a directive body are **not** reported.

**Edit candidates** — document `"## Plan\n\nShip beta on Nov 1\n\n## Risks\n\nVendor ships Nov 1 too\nStaffing gap\n"`:

| Edit | Outcome |
|---|---|
| `old="Nov 1"` | `edit_conflict`, matches 2, candidates `[{line:3,section:plan,snippet:"Ship beta on Nov 1"},{line:7,section:risks,…}]` |
| `old="Staffing  gap"` (double space) | matches 0, one candidate `{line:8, section:risks, snippet:"Staffing gap"}` |
| `old="Staffing gapp"`, scoped to `risks` | matches 0, candidate line 8 (absolute numbering) |
| `old="Staffing gap"`, scoped to `plan` | matches 0 (cannot see outside the scope) |
| `old="quarterly revenue forecast"` | matches 0, **no** candidates |
| a 4,000-line page, near-miss of one line | answers in well under 2 s |


## Appendix D: Sanitizer allowlist (v1)

Closed lists. Everything not listed is removed (tags are dropped, their text kept; `script`/`style` are removed with their content). The sanitizer MUST NOT permit `script`, `style`, `iframe`, `object`, `embed`, `svg`, `form` controls, `img` or any `on*`/`style` attribute.

**Tags:** `a`, `abbr`, `article`, `aside`, `blockquote`, `br`, `caption`, `code`, `dd`, `del`, `details`, `div`, `dl`, `dt`, `em`, `figcaption`, `figure`, `h2`, `h3`, `h4`, `h5`, `h6`, `hr`, `ins`, `kbd`, `li`, `mark`, `nav`, `ol`, `p`, `pre`, `s`, `section`, `small`, `span`, `strong`, `sub`, `summary`, `sup`, `table`, `tbody`, `td`, `tfoot`, `th`, `thead`, `time`, `tr`, `ul`.

**Attributes:**

| On | Allowed attributes |
|---|---|
| every tag | `aria-label`, `data-align`, `data-component`, `data-kind`, `data-recommended`, `data-role`, `data-status`, `id`, `lang`, `title` |
| `<a>` | `href` |
| `<th>` | `colspan`, `rowspan`, `scope` |
| `<td>` | `colspan`, `rowspan` |
| `<ol>` | `start` |
| `<details>` | `open` |
| `<time>` | `datetime` |

**URL schemes:** `http`, `https`, `mailto` (relative and `#fragment` URLs also pass). **Links** get `rel="noopener noreferrer"`. **Comments** are stripped.


## Appendix E: Web server reference configuration (nginx)

Wildcard-subdomain pages and a separate API host. Written for the reference deployment; **not exercised end to end** (§15.4).

`deploy/nginx/pages.conf`

```nginx
# Serves published pages (read-only) and fronts the write API.
# Pages:  http://<page-id>.pages.localhost:8080/   (use TLS + your internal CA in the VPC)
# API:    http://api.pages.localhost:8080/api/v1/...   and   /mcp/

limit_req_zone $binary_remote_addr zone=pagehost_api:10m rate=20r/s;

# ---- published pages: one origin per page (<id>.pages.<domain>) -------------------------
server {
    listen 80;
    server_name ~^(?<pid>[a-z0-9][a-z0-9-]{2,62})\.pages\.localhost$;

    # allow 10.0.0.0/8;  deny all;      # <- restrict to your VPC / VPN ranges in production

    # Shared theme assets (the stylesheet). `_assets` can never be a page id (ids start alphanumeric).
    location /_assets/ {
        alias /srv/pages/_assets/;
        add_header Cache-Control "public, max-age=3600" always;
        include /etc/nginx/snippets/pagehost-security.conf;
    }

    location / {
        root /srv/pages/$pid/current;
        try_files $uri $uri/ =404;
        include /etc/nginx/snippets/pagehost-security.conf;
    }
}

# ---- write API + MCP (exact name wins over the regex server above) ----------------------
server {
    listen 80;
    server_name api.pages.localhost;

    # allow 10.0.0.0/8;  deny all;

    client_max_body_size 2m;
    limit_req zone=pagehost_api burst=40 nodelay;

    location / {
        proxy_pass http://api:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_buffering off;          # MCP streamable HTTP / SSE
        proxy_read_timeout 300s;
    }
}
```

`deploy/nginx/pagehost-security.conf` (included by every location)

```nginx
# No script-src at all: agent content cannot run JavaScript even if a sanitizer bug slipped through.
add_header Content-Security-Policy "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer" always;
add_header X-Frame-Options "DENY" always;
```


## Appendix F: Error codes

| Code | HTTP | Raised when | `details` keys |
|---|---|---|---|
| `invalid_page_id` | 422 | An id argument does not match the id pattern | |
| `page_not_found` | 404 | Page missing or soft-deleted | |
| `version_not_found` | 404 | Requested version number does not exist | |
| `section_not_found` | 404 | Unknown section id | `section`, `available[≤50]`, `total_sections` |
| `page_exists` | 409 | Id allocation failed after 5 attempts | |
| `version_conflict` | 409 | The page changed since the mutation read it (or REST `base_version` is stale) | `expected_version`, `current_version` |
| `edit_conflict` | 409 | `old` matched 0 or ≥2 times | `matches`, `candidates[≤3]`; REST also `edit_index`, `current_source` |
| `invalid_content` | 422 | Empty/over-long title; empty content or `old`; empty edit list; content cannot be compiled | |
| `content_too_large` | 413 | Resulting source exceeds `max_source_bytes` | |
| `unknown_format` | 422 | Requested format is not registered | `available` |
| `unsupported_operation` | 422 | Section operation on a format without `SectionedFormat` | `format` |
| `unauthorized` | 401 | Missing or wrong bearer token | |
| `internal_error` | 500 | Anything unexpected (log it; do not leak internals) | |


## Appendix G: Scenario index (what each end-to-end case pins)

Generated from the scenario files. `planned` = specified, expected to fail until built.

**01 · publish-a-page**  
A page is created from a title and a Markdown body. It is served at the returned URL, reads back exactly as written, and renders headings, inline marks, bullets and numbered steps.  
*Calls:* `publish_page`

**02 · append-to-the-end-of-a-page**  
Appending needs no read and no anchor. The new block lands after everything else, and the result is lean: a version number and a change summary, not the page or its URL.  
*Calls:* `publish_page` → `append_page`

**03 · append-inside-a-section-and-add-a-sibling**  
Content can be appended to the end of a named section. Appending a block that starts with a heading, at the end of a section, creates a new sibling section right after it, and that new section is immediately addressable by its own id.  
*Calls:* `publish_page` → `append_page` → `append_page` → `read_page`

**04 · scoped-replace-text-resolves-ambiguity**  
A phrase that appears twice cannot be edited blindly: the call fails, changes nothing, and says where each occurrence is. Scoping the same edit to one section makes it unambiguous.  
*Calls:* `publish_page` → `replace_text` → `replace_text`

**05 · a-near-miss-edit-points-at-the-right-line**  
When the text to replace is not found (a slip in wording), the error names the closest line and its section instead of dumping the page, so the next attempt can succeed without a re-read.  
*Calls:* `publish_page` → `replace_text` → `replace_text`

**06 · replace-a-section-including-its-subsections**  
Replacing a section rewrites everything under its heading, nested subsections included, without quoting the old text. The removed subsection stops being addressable.  
*Calls:* `publish_page` → `replace_section` → `read_page`

**07 · a-replacement-without-a-heading-is-flagged**  
If replacement content for a section does not start with a heading, the section's heading is gone. The edit still applies, but the caller is warned so it can repair the page.  
*Calls:* `publish_page` → `replace_section`

**08 · delete-a-section**  
Deleting a section removes its heading, its text and its subsections. What was inside it can no longer be addressed.  
*Calls:* `publish_page` → `delete_section` → `delete_section` → `delete_section`

**09 · duplicate-headings-get-numbered-section-ids**  
Two headings with the same title are told apart by number: the first is `option`, the second `option-2`. Reads and edits scoped to a section hit the right one.  
*Calls:* `publish_page` → `read_page` → `replace_text` → `read_page`

**10 · replace-the-whole-page-and-rename-it**  
A full rewrite can also change the title. Leaving the title out keeps the current one.  
*Calls:* `publish_page` → `replace_page` → `replace_page`

**11 · rollback-restores-an-earlier-version**  
Rolling back does not rewind history: it adds a new version whose content equals the chosen one. The served page is the old page again and the history now has four entries.  
*Calls:* `publish_page` → `append_page` → `replace_text` → `rollback_page` → `list_versions`

**12 · an-edit-that-changes-nothing-adds-no-version**  
Replacing text with identical text is reported (a warning) but does not clutter the history with a duplicate version.  
*Calls:* `publish_page` → `replace_text`

**13 · a-large-page-is-read-section-by-section**  
Reading a large page does not return its whole text. It returns an outline of section ids, from which one section can be read and edited. The rest of the page is untouched.  
*Calls:* `publish_page` → `read_page` → `read_page` → `replace_text` → `read_page`

**14 · rereading-an-unchanged-page-is-cheap**  
A caller that remembers the version it last saw can ask again with `since`. If nothing changed it gets a tiny "unchanged" answer instead of the text; if the page moved on, it gets the text.  
*Calls:* `publish_page` → `read_page` → `read_page` → `append_page` → `read_page`

**15 · deleting-a-page-takes-it-offline**  
Once deleted, a page is no longer served at its URL, cannot be read or edited, and no longer appears in listings.  
*Calls:* `publish_page` → `list_pages` → `delete_page` → `read_page` → `append_page` → `list_pages`

**16 · listing-and-finding-pages**  
Pages can be found by a title fragment (case-insensitively), the result reports the total even when the list is cut short, and each entry has what is needed to link to it.  
*Calls:* `publish_page` → `publish_page` → `publish_page` → `list_pages` → `list_pages` → `list_pages`

**17 · hostile-content-is-neutralised**  
Whatever an author (or an agent that read untrusted text) writes, the served page can never run code or load anything from elsewhere. Ordinary text around it survives, and the caller is told that something was not supported.  
*Calls:* `publish_page`

**18 · markdown-feature-tour**  
The supported authoring features render as the structures a reader expects: a quote, a table, strikethrough, a code block, a callout and a collapsible section.  
*Calls:* `publish_page`

**19 · a-status-page-built-from-components** *(planned)*  
SPEC FOR THE NEXT STEP. A status page written with the planned components: a warning callout, a table of contents, a metrics row with statuses, a dated timeline with statuses, and a table from compact rows. Expected to fail until those components are built; then flip to `ready`. (A bare `:::toc` line is opened and closed like every other block.)  
*Calls:* `publish_page`

**20 · weekly-status-report-lifecycle**  
A realistic session over one page: publish a weekly report, update a table cell, add a note under the table, resolve a risk, and record a decision. Five versions later the page reads as a clean current report.  
*Calls:* `publish_page` → `replace_text` → `append_page` → `replace_section` → `append_page` → `read_page`


## Appendix H: Scenario file format and snapshot rules (for implementing a runner)

**File** (YAML):

```yaml
name: append-to-the-end-of-a-page      # equals the file name after the NN- prefix
status: ready                          # or planned (expected to fail, strictly)
description: ...
steps:
  - call: publish_page                 # a public tool name
    as: page                           # save the result; use ${page.id}, ${page.url} later
    args: {title: ..., content: "..."} # ${...} references and generators are expanded
    expect: {version: 1}               # partial match on the tool result
  - call: replace_text
    args: {id: "${page.id}", old: x, new: y}
    expect_error: {code: edit_conflict, details: {matches: 0}}   # the call must fail this way
final:                                 # one mapping, or a list of them
  page: page                           # which saved result (default: the first with a url)
  versions: 2                          # len(list_versions(id, limit=1000))
  source: |-                           # read_page(id, full=true).source, trailing whitespace ignored
    ...
  source_contains: [..]   source_excludes: [..]
  page_text_contains: [..]   page_text_excludes: [..]        # visible text of <main>
  snapshot: {title: ..., blocks: [...]}   # exact; or blocks_include: [...] (ordered subsequence)
  gone: true                           # the URL must no longer serve a page
```

**Variables and generators.** `${name.field}` resolves against saved results and run variables; a string that
is exactly one reference keeps the value's type. `${unique}` is a per-run random token. `{gen: repeat, count: N,
var: i, join: "\n", template: …}` and `{gen: concat, parts: […]}` build large inputs; inside a template,
`{i}` is replaced by the loop variable (other braces are left alone).

**Matchers** (in `expect` / `expect_error`): a plain value must equal; a mapping is a **subset** match; a
mapping made only of directives is a matcher: `{matches: regex}`, `{contains: x}` (substring of a string, or an
element of a list that equals or matches `x`), `{not_contains: x}`, `{length: n}`, `{min_length: n}`,
`{absent: true}` (the key must not exist), `{any: true}` (the key must exist). Lists compare element-wise and
must be the same length. YAML numbers compare equal to the same number; page text is always text.

**Execution.** For each step, call the tool through MCP; on a tool error, parse the JSON text into
`{code, message, details}`. After all steps, for each `final` check: fetch the saved page's `url` (a missing or
404 page fails unless `gone: true`), verify it is **inert** (§10.3), then run the listed checks.

**Snapshot** = `{title, blocks}` from the served HTML. `title` is the `<h1>` outside `<main>` (else `<title>`).
`blocks` come from `<main>` children in order; unknown wrapper elements (`div`, `section`, …) are looked
through; empty blocks are dropped. Inline marks are written as `**strong**`, `*em*`, `` `code` ``, `~~del~~`,
`[text](href)`, a `<br>` as a newline; other inline tags contribute only their text.

| Block key | Value |
|---|---|
| `h1`…`h6`, `p` | the text with inline marks |
| `ul`, `ol` | list of item texts; an item with a nested list is `{text, ul\|ol}` |
| `table` | `{head: [cell…], rows: [[cell…]…]}` |
| `pre` | code text (final newline removed); `blockquote`: paragraphs joined by `\n`; `hr`: `true` |
| `callout` | `{kind (data-kind, default note), title? (leading <strong>), text}` for any `<aside>` |
| `details` | `{summary, text, open? (true if the attribute is present)}` |
| `toc` | list of `"{link text} -> {href}"` |
| `stats` | list of `{label, value, delta?, status?}` (status from `data-status` on the row) |
| `timeline` | list of `{when (the `datetime` attribute, else the text), title, status?}` |
| `compare` | list of `{title (without the flag), recommended?, summary?, pros[], cons[]}` |

Two implementations that serve the same page MUST produce the same snapshot.

