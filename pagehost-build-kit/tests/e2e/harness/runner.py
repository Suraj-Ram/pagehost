"""Executes a scenario against *any* implementation.

All it needs is a ``Session`` (call a tool by name, get its result or a ``ToolFailure``) and a
``fetch(url) -> html`` (what a browser would get). Neither is implementation specific.
"""
from __future__ import annotations

import difflib
import json
from typing import Any, Awaitable, Callable, Protocol

import yaml

from .matchers import MISSING, match
from .scenario import Scenario, expand, new_run_vars
from .snapshot import inert_violations, snapshot, visible_text


class ToolFailure(Exception):
    """A tool call that the system reported as failed (the public error contract)."""

    def __init__(self, code: str, message: str = "", details: dict | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.details = code, message, details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class PageNotServed(Exception):
    """The page's URL did not return a page (404 / gone)."""


class Session(Protocol):
    async def call(self, tool: str, args: dict[str, Any]) -> Any: ...


Fetch = Callable[[str], str]


class ScenarioFailed(AssertionError):
    pass


async def run(scn: Scenario, session: Session, fetch: Fetch) -> dict[str, Any]:
    """Run a scenario; on success return {"vars": saved results, "saved": names of saved pages}."""
    vars: dict[str, Any] = new_run_vars()
    saved: list[str] = []

    def fail(where: str, problems: list[str] | str) -> None:
        body = problems if isinstance(problems, str) else "\n  - " + "\n  - ".join(problems)
        raise ScenarioFailed(f"[{scn.name}] {where}: {body}")

    for n, step in enumerate(scn.steps, 1):
        tool = step["call"]
        args = expand(step.get("args", {}), vars)
        where = f"step {n} {tool}({_brief(args)})"
        result: Any = MISSING
        failure: ToolFailure | None = None
        try:
            result = await session.call(tool, args)
        except ToolFailure as f:
            failure = f

        if "expect_error" in step:
            if failure is None:
                fail(where, f"expected the call to fail, but it returned {_brief(result)}")
            problems = match(expand(step["expect_error"], vars), failure.as_dict())
            if problems:
                fail(where, problems + [f"actual error: {failure.as_dict()}"])
            continue
        if failure is not None:
            fail(where, f"unexpected failure {failure.as_dict()}")
        if "expect" in step:
            problems = match(expand(step["expect"], vars), result)
            if problems:
                fail(where, problems + [f"actual result: {_brief(result, 400)}"])
        if "as" in step:
            vars[step["as"]] = result
            if isinstance(result, dict) and "url" in result:
                saved.append(step["as"])

    for k, check in enumerate(scn.final, 1):
        await _final(scn, f"final check {k}", expand(check, vars), session, fetch, vars, saved, fail)
    return {"vars": vars, "saved": saved}


async def _final(scn, where, check, session, fetch, vars, saved, fail) -> None:
    name = check.get("page") or (saved[0] if saved else None)
    if name is None or name not in vars:
        fail(where, "no saved page to check (give a publish step an `as:` name)")
    page = vars[name]

    if check.get("gone"):
        try:
            fetch(page["url"])
        except PageNotServed:
            return
        fail(where, f"{page['url']} is still being served")

    try:
        html = fetch(page["url"])
    except PageNotServed:
        fail(where, f"{page['url']} is not being served")

    problems = [f"served page is not inert: {v}" for v in inert_violations(html)]

    if any(k in check for k in ("source", "source_contains", "source_excludes")):
        source = (await session.call("read_page", {"id": page["id"], "full": True}))["source"]
        if "source" in check and source.rstrip() != str(check["source"]).rstrip():
            problems.append("source differs:\n" + _diff(str(check["source"]).rstrip(), source.rstrip()))
        problems += [f"source should contain {s!r}" for s in check.get("source_contains", []) if s not in source]
        problems += [f"source should not contain {s!r}" for s in check.get("source_excludes", []) if s in source]

    if "versions" in check:
        versions = await session.call("list_versions", {"id": page["id"], "limit": 1000})
        if len(versions) != check["versions"]:
            problems.append(f"expected {check['versions']} versions, found {len(versions)}")

    text = visible_text(html)
    problems += [f"page text should contain {s!r}" for s in check.get("page_text_contains", []) if s not in text]
    problems += [f"page text should not contain {s!r}" for s in check.get("page_text_excludes", []) if s in text]

    if "snapshot" in check:
        problems += _compare_snapshot(check["snapshot"], snapshot(html))

    if problems:
        fail(where, problems)


def _compare_snapshot(expected: dict, actual: dict) -> list[str]:
    out: list[str] = []
    if "title" in expected and _plain(expected["title"]) != actual["title"]:
        out.append(f"page title: expected {expected['title']!r}, got {actual['title']!r}")
    if "blocks" in expected:
        want, got = _plain(expected["blocks"]), actual["blocks"]
        if want != got:
            out.append("page blocks differ (- expected, + actual):\n" + _diff(_dump(want), _dump(got)))
    if "blocks_include" in expected:
        want, got = _plain(expected["blocks_include"]), actual["blocks"]
        it = iter(got)
        missing = [w for w in want if not any(w == g for g in it)]
        if missing:
            out.append("page is missing (in this order) the blocks:\n" + _dump(missing)
                       + "\nactual blocks:\n" + _dump(got))
    return out


def _plain(x: Any) -> Any:
    """YAML turns `120` into an int; page text is always text."""
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_plain(v) for v in x]
    if isinstance(x, bool) or x is None:
        return x
    return str(x) if isinstance(x, (int, float)) else x


def _dump(x: Any) -> str:
    return yaml.safe_dump(x, sort_keys=False, allow_unicode=True, width=100)


def _diff(a: str, b: str) -> str:
    return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), "expected", "actual", lineterm="", n=2))


def _brief(x: Any, limit: int = 140) -> str:
    s = json.dumps(x, default=str, ensure_ascii=False)
    return s if len(s) <= limit else s[: limit - 3] + "..."
