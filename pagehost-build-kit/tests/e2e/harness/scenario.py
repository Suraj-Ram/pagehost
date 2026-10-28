"""Scenario files: data in, expanded values out. Knows nothing about any implementation."""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VAR = re.compile(r"\$\{([\w.]+)\}")
CTX = re.compile(r"\{(\w+)\}")


@dataclass
class Scenario:
    name: str
    description: str
    status: str  # "ready" | "planned" (planned scenarios are expected to fail until built)
    steps: list[dict[str, Any]]
    final: list[dict[str, Any]]
    path: Path = field(default=Path("."))


def load(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text())
    final = raw.get("final") or []
    return Scenario(
        name=raw["name"], description=raw.get("description", ""), status=raw.get("status", "ready"),
        steps=raw["steps"], final=[final] if isinstance(final, dict) else final, path=path,
    )


def load_all(directory: Path) -> list[Scenario]:
    return [load(p) for p in sorted(directory.glob("*.yaml"))]


def new_run_vars() -> dict[str, Any]:
    return {"unique": secrets.token_hex(4)}


# ---- expansion -------------------------------------------------------------------------------


def expand(node: Any, vars: dict[str, Any], local: dict[str, Any] | None = None) -> Any:
    """Resolve ``${name.field}`` against saved results/run variables and expand generators.

    A string that is exactly one ``${...}`` keeps the referenced value's type."""
    local = local or {}
    if isinstance(node, dict):
        if "gen" in node:
            return _generate(node, vars, local)
        return {k: expand(v, vars, local) for k, v in node.items()}
    if isinstance(node, list):
        return [expand(v, vars, local) for v in node]
    if isinstance(node, str):
        whole = VAR.fullmatch(node)
        if whole:
            return _lookup(whole.group(1), vars)
        node = VAR.sub(lambda m: str(_lookup(m.group(1), vars)), node)
        return CTX.sub(lambda m: str(local[m.group(1)]) if m.group(1) in local else m.group(0), node)
    return node


def _lookup(dotted: str, vars: dict[str, Any]) -> Any:
    cur: Any = vars
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(f"${{{dotted}}} is not defined (is the step that saves it before this one?)")
        cur = cur[part]
    return cur


def _generate(spec: dict, vars: dict[str, Any], local: dict[str, Any]) -> str:
    kind = spec["gen"]
    if kind == "concat":
        return "".join(str(expand(p, vars, local)) for p in spec["parts"])
    if kind == "repeat":
        var = spec.get("var", "i")
        parts = [str(expand(spec["template"], vars, {**local, var: i})) for i in range(1, int(spec["count"]) + 1)]
        return str(spec.get("join", "\n")).join(parts)
    raise ValueError(f"unknown generator {kind!r}")
