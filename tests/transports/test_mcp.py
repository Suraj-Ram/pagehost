"""MCP transport contract against a fake PageService."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastmcp import Client

from pagehost.config import Settings
from pagehost.domain.errors import EditConflict, SectionNotFound
from pagehost.domain.models import (
    Mutation,
    Outline,
    OutlineEntry,
    PageSummary,
    Published,
    SectionView,
    SourceView,
    VersionInfo,
)
from pagehost.transports.mcp import build_mcp

_SPEC = Path(__file__).resolve().parents[2] / "pagehost-build-kit" / "SPEC.md"
_TOOLS = (
    "publish_page",
    "read_page",
    "append_page",
    "replace_text",
    "replace_section",
    "delete_section",
    "replace_page",
    "list_pages",
    "list_versions",
    "rollback_page",
    "delete_page",
)


class FakePageService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.errors: dict[str, Exception] = {}
        self.published = Published(id="q4", url="https://q4.pages.example/", version=1)
        self.mutation = Mutation(version=2, changed="+1/-0")
        self.source = SourceView(version=1, source="hello")
        self.section = SectionView(version=1, section="goals", source="## Goals\n")
        self.page_outline = Outline(version=1, tokens=1, sections=())
        self.pages = (
            1,
            (PageSummary(id="q4", title="Q4", version=1, url="https://q4.pages.example/"),),
        )
        self.versions = (
            VersionInfo(
                version=1,
                by="agent",
                at=datetime(2026, 10, 28, 0, 50, tzinfo=timezone.utc),
                summary="created",
            ),
        )

    def publish(self, title, content, *, author, summary=None, format=None):
        return self._result(
            "publish",
            title=title,
            content=content,
            author=author,
            summary=summary,
            format=format,
            result=self.published,
        )

    def read_source(self, page_id, *, version=None):
        return self._result("read_source", page_id=page_id, version=version, result=self.source)

    def read_section(self, page_id, section, *, version=None):
        return self._result(
            "read_section",
            page_id=page_id,
            section=section,
            version=version,
            result=self.section,
        )

    def outline(self, page_id, *, version=None):
        return self._result(
            "outline", page_id=page_id, version=version, result=self.page_outline
        )

    def append(self, page_id, content, *, section=None, author, summary=None, base_version=None):
        return self._result(
            "append",
            page_id=page_id,
            content=content,
            section=section,
            author=author,
            summary=summary,
            base_version=base_version,
            result=self.mutation,
        )

    def replace_text(
        self,
        page_id,
        old,
        new,
        *,
        section=None,
        author,
        summary=None,
        base_version=None,
    ):
        return self._result(
            "replace_text",
            page_id=page_id,
            old=old,
            new=new,
            section=section,
            author=author,
            summary=summary,
            base_version=base_version,
            result=self.mutation,
        )

    def replace_section(
        self,
        page_id,
        section,
        content,
        *,
        author,
        summary=None,
        base_version=None,
    ):
        return self._result(
            "replace_section",
            page_id=page_id,
            section=section,
            content=content,
            author=author,
            summary=summary,
            base_version=base_version,
            result=self.mutation,
        )

    def delete_section(self, page_id, section, *, author, summary=None, base_version=None):
        return self._result(
            "delete_section",
            page_id=page_id,
            section=section,
            author=author,
            summary=summary,
            base_version=base_version,
            result=self.mutation,
        )

    def replace_page(
        self,
        page_id,
        content,
        *,
        title=None,
        author,
        summary=None,
        base_version=None,
        format=None,
    ):
        return self._result(
            "replace_page",
            page_id=page_id,
            content=content,
            title=title,
            author=author,
            summary=summary,
            base_version=base_version,
            format=format,
            result=self.mutation,
        )

    def list_pages(self, *, query=None, limit=20):
        return self._result("list_pages", query=query, limit=limit, result=self.pages)

    def list_versions(self, page_id, *, limit=None):
        return self._result("list_versions", page_id=page_id, limit=limit, result=self.versions)

    def rollback(self, page_id, to_version, *, author):
        return self._result(
            "rollback",
            page_id=page_id,
            to_version=to_version,
            author=author,
            result=self.mutation,
        )

    def delete(self, page_id):
        return self._result("delete", page_id=page_id, result=None)

    def _result(self, name, *, result, **payload):
        self.calls.append((name, payload))
        error = self.errors.get(name)
        if error is not None:
            raise error
        return result


def test_tool_catalogue_matches_the_appendix(tmp_path: Path):
    server = build_mcp(FakePageService(), _settings(tmp_path))
    tools = _run(_list_tools(server))
    by_name = {tool.name: tool for tool in tools}

    assert server.name == "pagehost"
    assert tuple(tool.name for tool in tools) == _TOOLS
    assert "get_authoring_guide" not in by_name
    assert server.instructions == _appendix_a()
    assert len(server.instructions) < 2600

    descriptions = _appendix_b_descriptions()
    parameters = _appendix_b_parameters()
    assert set(by_name) == set(descriptions) == set(parameters)
    for name, tool in by_name.items():
        assert tool.description == descriptions[name]
        schema = tool.input_schema
        assert list(schema["properties"]) == [item[0] for item in parameters[name]]
        assert schema.get("required", []) == [item[0] for item in parameters[name] if item[1]]
        for param, _required, default in parameters[name]:
            if default is not _MISSING:
                assert schema["properties"][param]["default"] == default
        assert "summary" not in schema["properties"]
        assert "format" not in schema["properties"]
        assert "base_version" not in schema["properties"]

    listed = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in tools
        ],
        separators=(",", ":"),
    )
    assert len(listed) < 9000


def test_empty_warnings_are_omitted_and_author_comes_from_settings(tmp_path: Path):
    service = FakePageService()
    server = build_mcp(service, _settings(tmp_path, mcp_author="ada"))

    published = _run(_call(server, "publish_page", {"title": "Q4", "content": "body"}))
    assert published == {"id": "q4", "url": "https://q4.pages.example/", "version": 1}
    assert "warnings" not in published
    assert service.calls[-1] == (
        "publish",
        {
            "title": "Q4",
            "content": "body",
            "author": "ada",
            "summary": None,
            "format": None,
        },
    )

    edited = _run(_call(server, "append_page", {"id": "q4", "content": "- more"}))
    assert edited == {"version": 2, "changed": "+1/-0"}
    assert "warnings" not in edited
    assert service.calls[-1][1]["author"] == "ada"
    assert service.calls[-1][1]["summary"] is None
    assert service.calls[-1][1]["base_version"] is None

    service.mutation = Mutation(version=3, changed="+1/-1", warnings=("kept",))
    warned = _run(
        _call(server, "replace_text", {"id": "q4", "old": "Ship beta", "new": "Ship GA"})
    )
    assert warned == {"version": 3, "changed": "+1/-1", "warnings": ["kept"]}
    assert service.calls[-1][1]["summary"] is None
    assert service.calls[-1][1]["base_version"] is None


def test_edit_conflict_json_drops_current_source_and_edit_index(tmp_path: Path):
    service = FakePageService()
    service.errors["replace_text"] = EditConflict(
        "edit 0 matched 0 times; old_str must match exactly once",
        matches=0,
        candidates=[{"line": 3, "snippet": "- Ship beta", "section": "goals"}],
        current_source="SECRET_SOURCE",
        edit_index=0,
    )
    server = build_mcp(service, _settings(tmp_path))

    result = _run(
        _call_mcp(server, "replace_text", {"id": "q4", "old": "Ship betta", "new": "Ship GA"})
    )

    assert result.is_error is True
    assert len(result.content) == 1
    text = result.content[0].text
    assert text.startswith("{")
    assert text == json.dumps(json.loads(text), separators=(",", ":"))
    assert "SECRET_SOURCE" not in text
    assert "current_source" not in text
    assert "edit_index" not in text
    body = json.loads(text)
    assert body == {
        "code": "edit_conflict",
        "message": "edit 0 matched 0 times; old_str must match exactly once",
        "details": {
            "matches": 0,
            "candidates": [{"line": 3, "snippet": "- Ship beta", "section": "goals"}],
        },
    }


def test_since_returns_unchanged_without_source_even_when_section_is_set(tmp_path: Path):
    service = FakePageService()
    service.source = SourceView(version=4, source="## Goals\n\n- Ship beta\n")
    service.section = SectionView(version=4, section="goals", source="## Goals\n\n- Ship beta\n")
    server = build_mcp(service, _settings(tmp_path))

    unchanged = _run(_call(server, "read_page", {"id": "q4", "since": 4}))
    assert unchanged == {"version": 4, "unchanged": True}
    assert "source" not in unchanged
    assert [name for name, _payload in service.calls] == ["read_source"]

    service.calls.clear()
    with_section = _run(_call(server, "read_page", {"id": "q4", "section": "goals", "since": 4}))
    assert with_section == {"version": 4, "unchanged": True}
    assert "source" not in with_section
    assert "section" not in with_section
    assert [name for name, _payload in service.calls] == ["read_section"]

    service.calls.clear()
    section = _run(_call(server, "read_page", {"id": "q4", "section": "goals", "since": 3}))
    assert section == {
        "version": 4,
        "section": "goals",
        "source": "## Goals\n\n- Ship beta\n",
    }

    service.errors["read_section"] = SectionNotFound(
        "no section 'nope'",
        section="nope",
        available=["goals"],
        total_sections=1,
    )
    missing = _run(
        _call_mcp(server, "read_page", {"id": "q4", "section": "nope", "since": 4})
    )
    assert missing.is_error is True
    assert json.loads(missing.content[0].text)["code"] == "section_not_found"


def test_big_page_outline_and_the_read_threshold(tmp_path: Path):
    service = FakePageService()
    small = "x" * 12
    service.source = SourceView(version=2, source=small)
    server = build_mcp(service, _settings(tmp_path, full_read_tokens=3))

    assert _estimated_boundary(small) == 3
    exact = _run(_call(server, "read_page", {"id": "q4"}))
    assert exact == {"version": 2, "source": small}
    assert "outline" not in [name for name, _payload in service.calls]

    big = "y" * 13
    service.source = SourceView(version=5, source=big)
    service.page_outline = Outline(
        version=5,
        tokens=2500,
        sections=(
            OutlineEntry(id="goals", level=2, title="Goals", tokens=40),
            OutlineEntry(id="risks", level=3, title="Risks", tokens=12),
        ),
    )
    service.calls.clear()
    outlined = _run(_call(server, "read_page", {"id": "q4"}))
    assert outlined == {
        "version": 5,
        "tokens": 2500,
        "outline": ["goals h2 ~40t", "risks h3 ~12t"],
        "hint": "Big page. Re-call with section=<id> or full=true.",
    }
    assert [name for name, _payload in service.calls] == ["read_source", "outline"]

    service.calls.clear()
    full = _run(_call(server, "read_page", {"id": "q4", "full": True}))
    assert full == {"version": 5, "source": big}
    assert "outline" not in [name for name, _payload in service.calls]

    service.page_outline = Outline(version=5, tokens=2500, sections=())
    service.calls.clear()
    fallback = _run(_call(server, "read_page", {"id": "q4"}))
    assert fallback == {"version": 5, "source": big}
    assert [name for name, _payload in service.calls] == ["read_source", "outline"]


def test_remaining_tools_return_only_the_specified_fields(tmp_path: Path):
    service = FakePageService()
    service.versions = (
        VersionInfo(version=1, by="ada", at=datetime(2026, 10, 28, 0, 50), summary=None),
        VersionInfo(
            version=2,
            by="ada",
            at=datetime(2026, 10, 27, 20, 50, tzinfo=timezone(timedelta(hours=-4))),
            summary="edit text",
        ),
    )
    server = build_mcp(service, _settings(tmp_path, mcp_author="ada"))

    replaced = _run(
        _call(
            server,
            "replace_section",
            {"id": "q4", "section": "goals", "content": "## Goals\n"},
        )
    )
    assert replaced == {"version": 2, "changed": "+1/-0"}
    deleted = _run(_call(server, "delete_section", {"id": "q4", "section": "goals"}))
    assert set(deleted) == {"version", "changed"}
    rewritten = _run(_call(server, "replace_page", {"id": "q4", "content": "all"}))
    assert set(rewritten) == {"version", "changed"}
    assert service.calls[-1][1]["title"] is None
    assert service.calls[-1][1]["format"] is None
    assert service.calls[-1][1]["author"] == "ada"

    pages = _run(_call(server, "list_pages", {"query": "q4"}))
    assert pages == {
        "total": 1,
        "pages": [{"id": "q4", "title": "Q4", "version": 1, "url": "https://q4.pages.example/"}],
    }
    assert service.calls[-1][1]["limit"] == 20
    _run(_call(server, "list_pages", {"limit": 0}))
    assert service.calls[-1][1]["limit"] == 1

    versions = _run(_call(server, "list_versions", {"id": "q4"}))
    assert versions == [
        {"version": 1, "by": "ada", "at": "2026-10-28 00:50"},
        {"version": 2, "by": "ada", "at": "2026-10-28 00:50", "summary": "edit text"},
    ]
    assert service.calls[-1][1]["limit"] == 10
    _run(_call(server, "list_versions", {"id": "q4", "limit": -2}))
    assert service.calls[-1][1]["limit"] == 1

    rolled = _run(_call(server, "rollback_page", {"id": "q4", "to_version": 1}))
    assert rolled == {"version": 2, "changed": "+1/-0"}
    assert service.calls[-1][1]["author"] == "ada"
    removed = _run(_call(server, "delete_page", {"id": "q4"}))
    assert removed == {"deleted": True}


def _settings(tmp_path: Path, **overrides):
    values = {
        "data_dir": tmp_path,
        "token": "token",
        "url_template": "https://{id}.pages.example/",
    }
    values.update(overrides)
    return Settings(**values)


def _run(awaitable):
    return asyncio.run(awaitable)


async def _list_tools(server):
    async with Client(server) as client:
        return await client.list_tools()


async def _call(server, name: str, arguments: dict):
    async with Client(server) as client:
        return (await client.call_tool(name, arguments)).data


async def _call_mcp(server, name: str, arguments: dict):
    async with Client(server) as client:
        return await client.call_tool_mcp(name, arguments)


def _appendix_a() -> str:
    text = _SPEC.read_text(encoding="utf-8")
    marker = "```text\n"
    start = text.index(marker) + len(marker)
    end = text.index("```", start)
    return text[start:end]


def _appendix_b_descriptions() -> dict[str, str]:
    descriptions = {}
    for cells in _appendix_b_rows():
        descriptions[cells[0].strip("`")] = cells[2]
    return descriptions


_MISSING = object()


def _appendix_b_parameters() -> dict[str, list[tuple[str, bool, object]]]:
    parsed: dict[str, list[tuple[str, bool, object]]] = {}
    for cells in _appendix_b_rows():
        name = cells[0].strip("`")
        spec = cells[1].strip().strip("`")
        params: list[tuple[str, bool, object]] = []
        for part in spec.split(","):
            label, _, rest = part.strip().partition(":")
            required = not label.endswith("?")
            param = label[:-1] if label.endswith("?") else label
            default = _MISSING
            if "=" in rest:
                raw = rest.split("=", 1)[1].strip()
                if raw == "false":
                    default = False
                elif raw == "true":
                    default = True
                else:
                    default = int(raw)
            params.append((param, required, default))
        parsed[name] = params
    return parsed


def _appendix_b_rows() -> list[list[str]]:
    text = _SPEC.read_text(encoding="utf-8")
    section = text[text.index("## Appendix B:") : text.index("## Appendix C:")]
    rows = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def _estimated_boundary(source: str) -> int:
    return -(-len(source) // 4)
