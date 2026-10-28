"""Fail when a layer imports a layer SPEC §2.3 forbids."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pagehost"

_STDLIB = sys.stdlib_module_names | {"__future__"}


def test_layers_import_only_what_they_may():
    problems: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for imported in _imports(path):
            layer = _layer(path)
            if layer is None or _allowed(layer, imported, path):
                continue
            problems.append(f"{path.relative_to(ROOT)} imports {imported}")
    assert problems == []


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _layer(path: Path) -> str | None:
    relative = path.relative_to(PACKAGE)
    if relative.parts[0] == "domain":
        return "domain"
    if relative.parts[0] == "application":
        return "application"
    if relative.parts[0] == "adapters":
        return "adapters"
    if relative.parts[0] == "transports":
        return "transports"
    if path.name == "bootstrap.py":
        return "bootstrap"
    return "root"


def _allowed(layer: str, imported: str, path: Path) -> bool:
    top = imported.split(".", 1)[0]
    if top in _STDLIB:
        return True
    if layer == "bootstrap":
        return True
    if layer == "domain":
        return imported == "pagehost" or imported.startswith("pagehost.domain")
    if layer == "application":
        return imported == "pagehost" or imported.startswith(("pagehost.domain", "pagehost.application"))
    if layer == "adapters":
        if imported.startswith(("pagehost.application", "pagehost.transports", "pagehost.bootstrap")):
            return False
        if imported.startswith("pagehost.adapters."):
            own = f"pagehost.adapters.{path.stem}"
            return imported == own or imported.startswith(own + ".")
        return True
    if layer == "transports":
        return not imported.startswith(("pagehost.adapters", "pagehost.bootstrap"))
    return imported.startswith("pagehost")
