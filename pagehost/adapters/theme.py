"""Wrap a sanitized fragment in the page shell and serve the shared stylesheet."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path

from pagehost.domain.models import Document

_STYLESHEET = Path(__file__).resolve().parent.parent / "assets" / "pagehost.css"


class PagehostTheme:
    def render_document(self, document: Document) -> str:
        title = escape(document.title, quote=True)
        updated = _utc_stamp(document.updated_at)
        return (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="color-scheme" content="light dark">\n'
            f"<title>{title}</title>\n"
            '<link rel="stylesheet" href="/_assets/pagehost.css">\n'
            "</head>\n"
            "<body>\n"
            f"<header><h1>{title}</h1></header>\n"
            "<main>\n"
            f"{document.body_html}\n"
            "</main>\n"
            f"<footer>v{document.version} &middot; updated {updated}</footer>\n"
            "</body>\n"
            "</html>\n"
        )

    def static_assets(self) -> dict[str, bytes]:
        return {"pagehost.css": _STYLESHEET.read_bytes()}


def _utc_stamp(updated_at: datetime) -> str:
    if updated_at.tzinfo is not None:
        updated_at = updated_at.astimezone(timezone.utc)
    return updated_at.strftime("%Y-%m-%d %H:%M UTC")
