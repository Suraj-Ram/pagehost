# pagehost.css

A small (~16 KB), classless stylesheet in the spirit of Pico: write semantic HTML and it
looks right. Its one extra idea is that **meaning lives in the markup and looks live in the
stylesheet**: a blocked task is `data-status="blocked"`, never "red". Re-theming never touches content.

- No JavaScript, no `url()`, no web fonts, no images: works under `style-src 'self'` with `default-src 'none'`.
- Light and dark from the OS; force with `<html data-theme="dark|light">`.
- Everything is driven by `--ph-*` tokens.
- Verified in headless Chromium at desktop, phone (375px) and dark, plus all six OS x `data-theme` combinations.
  Not yet checked in Safari or Firefox.

```
PAGEHOST_THEME=pagehost   # default. "pico" selects the Pico CSS theme instead
```
Standalone use: `<link rel="stylesheet" href="pagehost.css">`, then `<header><h1>` / `<main>` / `<footer>`.

## Font

The stack is `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, ...`: the platform's own UI font on
each OS, and nothing to download. The font in the design preview was the chat app's own typeface, which isn't
distributable. To use a licensed font, self-host a `.woff2` in your site's `_assets`, declare `@font-face` in
your own stylesheet (this file stays `url()`-free; a test enforces it), and set `--ph-font-sans`.
Weights used: 400 and 500 only.

## Tokens

| Token | Meaning |
|---|---|
| `--ph-font-sans`, `--ph-font-mono` | Font stacks |
| `--ph-bg`, `--ph-surface`, `--ph-raised` | Page, tinted card (stats, code), raised card (compare) |
| `--ph-text`, `--ph-text-2`, `--ph-text-3` | Primary, secondary, muted text (all >= 4.5:1, tested) |
| `--ph-border`, `--ph-border-strong` | 0.5px hairlines |
| `--ph-link` | Link colour |
| `--ph-{accent,success,warning,danger}-{bg,fg,border,mark}` | Role colours: tint, text on tint, outline, marker/icon |
| `--ph-radius`, `--ph-radius-lg`, `--ph-page-width` | 8px, 12px, 44rem |

## Base elements (no markup needed)

`header > h1`, `main`, `footer` as the page shell; `h1..h6`, `p`, `ul/ol/li`, `a`, `strong/em/small/mark/del/kbd/code`,
`pre`, `blockquote`, `hr`, `table` (+ `caption`), `details/summary`, `dl`, `figure/figcaption`, `time`.
Tables scroll horizontally on phones. Numeric columns: add `data-align="end"` to the `th`/`td`.

## Status vocabulary

Used by stats, timelines and inline badges. The value carries the meaning; text is always shown, and each value
has its own marker shape, so it never relies on colour alone.

| `data-status` | Meaning | Marker | Role |
|---|---|---|---|
| `done` | Complete | check | success |
| `active` | In progress | play | accent |
| `at-risk` | Needs attention | triangle | warning |
| `blocked` | Cannot proceed | cross | danger |
| `planned` | Not started (also the default) | dot | neutral |

A badge is `<span data-role="status">Done</span>` inside, or carrying, a `data-status`.

## Components: the markup contract

Each component is the markup below. Anything that emits HTML (a directive renderer, another content format)
must produce exactly this shape. `tests/test_css.py` checks the sanitizer lets every one through unchanged.

**Callout** (kinds `note` (default) `warning` `success` `danger`; a bare `<aside>` is a note)
```html
<aside data-component="callout" data-kind="warning"><strong>Title</strong><p>Body.</p></aside>
```

**Table of contents** (headings need matching `id`s)
```html
<nav data-component="toc" aria-label="Contents"><p data-role="label">On this page</p>
<ol><li><a href="#summary">Summary</a></li></ol></nav>
```

**Stats**
```html
<dl data-component="stats">
  <div data-status="done"><dt>Revenue</dt><dd data-role="value">$5.2M</dd>
  <dd data-role="delta">+12%</dd><dd data-role="status">Done</dd></div>
</dl>
```
The status is explicit because a delta's direction doesn't say whether it's good: latency `+40 ms` is `blocked`.

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

**Details** and **table** are plain `<details><summary>` and `<table>`.

## Accessibility

Text and marker contrast are tested in both modes (WCAG AA 4.5:1 text, 3:1 non-text). Status and pros/cons carry
text or a label as well as colour and shape. Links are underlined. There is a visible focus ring. Smooth scrolling
and the chevron animation respect `prefers-reduced-motion`.

## Browser support

Current evergreen browsers (custom properties, grid, `clip-path`, `env()`). Where `clip-path` is unsupported, the
markers degrade to small solid squares, and the text still carries the meaning.

## Files

`src/pagehost/adapters/themes/assets/pagehost.css` is the library. `docs/showcase-fragment.html` is every component
in contract markup. `docs/showcase.html` is that fragment rendered through the real sanitizer and theme with the CSS
inlined, built by `python scripts/build_showcase.py`; a test fails if it is stale.
