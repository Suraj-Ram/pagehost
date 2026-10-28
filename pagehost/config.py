"""Process settings. The MVP accepts a bearer token and does not enforce it."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    token: str
    url_template: str
    max_source_bytes: int = 1_000_000
    default_format: str = "markdown"
    mcp_author: str = "agent"
    full_read_tokens: int = 1000

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", Path(self.data_dir))
        if "{id}" not in self.url_template:
            raise ValueError("url_template must contain {id}")
        if self.max_source_bytes < 1:
            raise ValueError("max_source_bytes must be positive")
        if self.full_read_tokens < 1:
            raise ValueError("full_read_tokens must be positive")

    @property
    def site_root(self) -> Path:
        return self.data_dir / "sites"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Read §11.1. `PAGEHOST_TOKEN` is required; everything else has a default.

        `PAGEHOST_BASE_URL` is the public origin of a deployment (`https://pages.example.com`).
        Page links are then `<base>/p/{id}/`. It replaces `PAGEHOST_URL_TEMPLATE`.
        """
        values = os.environ if env is None else env
        token = values.get("PAGEHOST_TOKEN", "")
        if token == "":
            raise ValueError("PAGEHOST_TOKEN is required")
        return cls(
            data_dir=Path(values.get("PAGEHOST_DATA_DIR", "data")),
            token=token,
            url_template=_url_template(values),
            max_source_bytes=int(values.get("PAGEHOST_MAX_SOURCE_BYTES", "1000000")),
            default_format=values.get("PAGEHOST_DEFAULT_FORMAT", "markdown"),
            mcp_author=values.get("PAGEHOST_MCP_AUTHOR", "agent"),
            full_read_tokens=int(values.get("PAGEHOST_MCP_FULL_READ_TOKENS", "1000")),
        )


def _url_template(values: Mapping[str, str]) -> str:
    base_url = values.get("PAGEHOST_BASE_URL", "").strip()
    if base_url:
        if "PAGEHOST_URL_TEMPLATE" in values:
            raise ValueError("set PAGEHOST_BASE_URL or PAGEHOST_URL_TEMPLATE, not both")
        return _template_from_base_url(base_url)
    return values.get(
        "PAGEHOST_URL_TEMPLATE",
        "https://{id}.pages.internal.example.com/",
    )


def _template_from_base_url(base_url: str) -> str:
    """Pages live at `<origin>/p/{id}/`, the path form of §9.3."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc == "":
        raise ValueError("PAGEHOST_BASE_URL must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("PAGEHOST_BASE_URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("PAGEHOST_BASE_URL must not include a query or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError(
            "PAGEHOST_BASE_URL must be an origin with no path; pages are served at <base>/p/<id>/"
        )
    return f"{parsed.scheme}://{parsed.netloc}/p/{{id}}/"
