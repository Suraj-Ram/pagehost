"""Tiny expectation language for tool results. Pure data in, list of mismatches out.

A plain value must equal the actual one. A mapping is a *subset* match (extra keys in the
actual result are fine). A mapping made only of directives is a matcher:

    {matches: "^https?://"}   regex search on a string
    {contains: X}             substring of a string, or a list element matching X
    {not_contains: X}         the opposite
    {length: 3} {min_length: 1}
    {absent: true}            the key must not be present
    {any: true}               the key must be present, whatever its value
"""
from __future__ import annotations

import re
from typing import Any

DIRECTIVES = {"matches", "contains", "not_contains", "length", "min_length", "absent", "any"}
MISSING = object()


def is_matcher(x: Any) -> bool:
    return isinstance(x, dict) and bool(x) and set(x) <= DIRECTIVES


def match(expected: Any, actual: Any, path: str = "$") -> list[str]:
    if is_matcher(expected):
        return _directives(expected, actual, path)
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected an object, got {_short(actual)}"]
        problems: list[str] = []
        for key, exp in expected.items():
            got = actual.get(key, MISSING)
            if got is MISSING:
                if not (is_matcher(exp) and exp.get("absent") is True):
                    problems.append(f"{path}.{key}: missing")
                continue
            problems += match(exp, got, f"{path}.{key}")
        return problems
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected a list of {len(expected)}, got {_short(actual)}"]
        return [p for i, (e, a) in enumerate(zip(expected, actual)) for p in match(e, a, f"{path}[{i}]")]
    return [] if _equal(expected, actual) else [f"{path}: expected {_short(expected)}, got {_short(actual)}"]


def _directives(exp: dict, actual: Any, path: str) -> list[str]:
    problems: list[str] = []
    if exp.get("absent") is True:
        if actual is not MISSING:
            problems.append(f"{path}: expected to be absent, got {_short(actual)}")
        return problems
    if actual is MISSING:
        return [f"{path}: missing"]
    if "matches" in exp and not (isinstance(actual, str) and re.search(exp["matches"], actual)):
        problems.append(f"{path}: {_short(actual)} does not match /{exp['matches']}/")
    if "contains" in exp and not _contains(exp["contains"], actual):
        problems.append(f"{path}: {_short(actual)} does not contain {_short(exp['contains'])}")
    if "not_contains" in exp and _contains(exp["not_contains"], actual):
        problems.append(f"{path}: {_short(actual)} unexpectedly contains {_short(exp['not_contains'])}")
    if "length" in exp and not (hasattr(actual, "__len__") and len(actual) == exp["length"]):
        problems.append(f"{path}: expected length {exp['length']}, got {_short(actual)}")
    if "min_length" in exp and not (hasattr(actual, "__len__") and len(actual) >= exp["min_length"]):
        problems.append(f"{path}: expected length >= {exp['min_length']}, got {_short(actual)}")
    return problems


def _contains(x: Any, actual: Any) -> bool:
    if isinstance(actual, str):
        return isinstance(x, str) and x in actual
    if isinstance(actual, list):
        return any(
            (isinstance(item, str) and isinstance(x, str) and x in item) or not match(x, item)
            for item in actual
        )
    return False


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return a == b


def _short(x: Any) -> str:
    s = "<absent>" if x is MISSING else repr(x)
    return s if len(s) <= 120 else s[:117] + "..."
