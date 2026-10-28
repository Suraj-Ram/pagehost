"""Inject one realistic fault at a time and confirm the scenario that pins it fails.

Breaking only the sanitizer stays invisible: Markdown still refuses raw HTML. Breaking
Markdown and the sanitizer together makes scenario 17 fail.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pagehost.adapters.publisher import FilesystemPublisher  # noqa: E402
from pagehost.adapters.sanitizer import Nh3Sanitizer  # noqa: E402
from pagehost.application.service import PagehostService  # noqa: E402
from pagehost.domain.errors import EditConflict  # noqa: E402
from pagehost.domain.models import RenderedFragment  # noqa: E402
from pagehost.domain.normalize import normalize_newlines  # noqa: E402
import pagehost.application.service as service_mod  # noqa: E402
import pagehost.transports.mcp as mcp  # noqa: E402


def _append_at_start(real):
    def append(self, page_id, content, *, section=None, author, summary=None, base_version=None):
        if section is not None:
            return real(
                self,
                page_id,
                content,
                section=section,
                author=author,
                summary=summary,
                base_version=base_version,
            )
        current = self._begin(page_id, base_version)
        new_source = normalize_newlines(content).rstrip("\n") + "\n\n" + current.source
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=new_source,
            author=author,
            summary=summary,
            generated="append",
        )

    return append


def _delete_keeps_files(real):
    def delete(self, page_id):
        self._current(page_id)
        self._pages.mark_deleted(page_id)

    return delete


def _ignore_section(real):
    def replace_text(self, page_id, old, new, *, section=None, author, summary=None, base_version=None):
        return real(
            self,
            page_id,
            old,
            new,
            section=None,
            author=author,
            summary=summary,
            base_version=base_version,
        )

    return replace_text


def _rollback_keeps_current(real):
    def rollback(self, page_id, to_version, *, author):
        current = self._current(page_id)
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=current.source,
            author=author,
            summary=None,
            generated=f"Rollback to v{to_version}",
            force=True,
        )

    return rollback


def _always_store(real):
    def _commit(self, *args, **kwargs):
        kwargs["force"] = True
        return real(self, *args, **kwargs)

    return _commit


def _keep_source(generated: str):
    def method(self, page_id, section, content=None, *, author, summary=None, base_version=None):
        current = self._begin(page_id, base_version)
        return self._commit(
            current,
            title=current.title,
            format_name=current.format,
            source=current.source,
            author=author,
            summary=summary,
            generated=generated.format(section=section),
        )

    return method


def _drop_candidates(real):
    def replace_exact(*args, **kwargs):
        try:
            return real(*args, **kwargs)
        except EditConflict as exc:
            matches = exc.details.get("matches", 0)
            raise EditConflict(exc.message, matches=matches, candidates=[]) from None

    return replace_exact


def _skip_publish(real):
    def publish(self, page_id, version, html):
        return None

    return publish


def _list_nothing(real):
    def list_pages(self, *, query=None, limit=20):
        return 0, ()

    return list_pages


def _ignore_since(real):
    def _read_page(service, settings, page_id, section, full, since):
        return real(service, settings, page_id, section, full, None)

    return _read_page


def _raw_fragment(self, source: str) -> RenderedFragment:
    return RenderedFragment(html=source, warnings=("raw html left in place",))


def _sanitizer_off(self, html: str) -> str:
    return html


FAULTS = (
    ("append writes at the start", "append-to-the-end-of-a-page", (patch.object(PagehostService, "append", _append_at_start(PagehostService.append)),), 1),
    ("delete forgets to unpublish", "deleting-a-page-takes-it-offline", (patch.object(PagehostService, "delete", _delete_keeps_files(PagehostService.delete)),), 1),
    ("section scope is ignored", "scoped-replace-text-resolves-ambiguity", (patch.object(PagehostService, "replace_text", _ignore_section(PagehostService.replace_text)),), 1),
    ("rollback keeps the current source", "rollback-restores-an-earlier-version", (patch.object(PagehostService, "rollback", _rollback_keeps_current(PagehostService.rollback)),), 1),
    ("an identical edit still stores a version", "an-edit-that-changes-nothing-adds-no-version", (patch.object(PagehostService, "_commit", _always_store(PagehostService._commit)),), 1),
    ("delete section leaves the source", "delete-a-section", (patch.object(PagehostService, "delete_section", _keep_source("delete section {section}")),), 1),
    ("replace section leaves the source", "replace-a-section-including-its-subsections", (patch.object(PagehostService, "replace_section", _keep_source("replace section {section}")),), 1),
    ("a near miss has no candidates", "a-near-miss-edit-points-at-the-right-line", (patch.object(service_mod, "replace_exact", _drop_candidates(service_mod.replace_exact)),), 1),
    ("publish writes nothing", "publish-a-page", (patch.object(FilesystemPublisher, "publish", _skip_publish(FilesystemPublisher.publish)),), 1),
    ("listing pages returns nothing", "listing-and-finding-pages", (patch.object(PagehostService, "list_pages", _list_nothing(PagehostService.list_pages)),), 1),
    ("since is ignored", "rereading-an-unchanged-page-is-cheap", (patch.object(mcp, "_read_page", _ignore_since(mcp._read_page)),), 1),
    ("markdown and the sanitizer both let HTML through", "hostile-content-is-neutralised", (
        patch("pagehost.adapters.markdown.MarkdownFormat.render", _raw_fragment),
        patch.object(Nh3Sanitizer, "clean", _sanitizer_off),
    ), 1),
    ("only the sanitizer is bypassed", "hostile-content-is-neutralised", (patch.object(Nh3Sanitizer, "clean", _sanitizer_off),), 0),
)


@contextmanager
def _applied(patches) -> Iterator[None]:
    for item in patches:
        item.start()
    try:
        yield
    finally:
        for item in reversed(patches):
            item.stop()


def _run(scenario: str) -> int:
    return int(
        pytest.main(
            [
                "pagehost-build-kit/tests/e2e",
                "-k",
                scenario,
                "--tb=line",
                "-p",
                "no:cacheprovider",
                "-o",
                "addopts=",
            ]
        )
    )


def main() -> int:
    os.chdir(ROOT)
    missed: list[str] = []
    for name, scenario, patches, expected in FAULTS:
        print(f"\n== {name} ({scenario}) ==", flush=True)
        with _applied(patches):
            code = _run(scenario)
        if code != expected:
            missed.append(f"{name}: exit {code}, expected {expected}")
            print(f"MISSED {name}", flush=True)
        else:
            print(f"ok {name}", flush=True)
    if missed:
        print("\n".join(missed), file=sys.stderr)
        return 1
    print(f"\n{len(FAULTS)} faults behaved as expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
