"""On-disk site publisher. Readers follow ``current`` and never see a partial page."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class FilesystemPublisher:
    """Serve ``<root>/<id>/current/index.html`` and shared files under ``_assets``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def publish(self, page_id: str, version: int, html: str) -> None:
        version_name = f"v{version}"
        version_dir = self._root / page_id / version_name
        version_dir.mkdir(parents=True, exist_ok=True)
        _write_bytes(version_dir / "index.html", html.encode("utf-8"))
        _swap_symlink(self._root / page_id / "current", version_name)

    def unpublish(self, page_id: str) -> None:
        (self._root / page_id / "current").unlink(missing_ok=True)

    def install_assets(self, assets: dict[str, bytes]) -> None:
        for name in assets:
            _require_asset_name(name)
        directory = self._root / "_assets"
        directory.mkdir(parents=True, exist_ok=True)
        for name, payload in assets.items():
            _write_bytes(directory / name, payload)


def _require_asset_name(name: str) -> None:
    separators = {os.sep, "/", "\\"}
    if os.altsep:
        separators.add(os.altsep)
    if name == "" or name.startswith(".") or any(separator in name for separator in separators):
        raise ValueError("asset name must not contain a path separator or start with '.'")


def _write_bytes(destination: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp is owner-only. Nginx runs as a different user and mounts this tree read-only.
        # TODO investigate the best way to handle this
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _swap_symlink(link: Path, target: str) -> None:
    directory = link.parent
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f".{link.name}-{os.getpid()}-{os.urandom(8).hex()}"
    try:
        os.symlink(target, temporary)
        os.replace(temporary, link)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
