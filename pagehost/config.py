"""Process settings. The MVP accepts a bearer token and does not enforce it."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


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
        """Read §11.1. `PAGEHOST_TOKEN` is required; everything else has a default."""
        values = os.environ if env is None else env
        token = values.get("PAGEHOST_TOKEN", "")
        if token == "":
            raise ValueError("PAGEHOST_TOKEN is required")
        return cls(
            data_dir=Path(values.get("PAGEHOST_DATA_DIR", "data")),
            token=token,
            url_template=values.get(
                "PAGEHOST_URL_TEMPLATE",
                "https://{id}.pages.internal.example.com/",
            ),
            max_source_bytes=int(values.get("PAGEHOST_MAX_SOURCE_BYTES", "1000000")),
            default_format=values.get("PAGEHOST_DEFAULT_FORMAT", "markdown"),
            mcp_author=values.get("PAGEHOST_MCP_AUTHOR", "agent"),
            full_read_tokens=int(values.get("PAGEHOST_MCP_FULL_READ_TOKENS", "1000")),
        )
