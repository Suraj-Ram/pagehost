"""Process settings. The MVP accepts a bearer token and does not enforce it."""

from __future__ import annotations

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
