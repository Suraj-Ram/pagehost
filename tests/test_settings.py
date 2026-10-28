from pathlib import Path

import pytest

from pagehost.config import Settings


def test_site_root_lives_under_the_data_dir(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        token="e2e-token",
        url_template="http://{id}.pages.e2e.test/",
    )

    assert settings.site_root == tmp_path / "sites"
    assert settings.token == "e2e-token"
    assert settings.max_source_bytes == 1_000_000
    assert settings.mcp_author == "agent"
    assert settings.full_read_tokens == 1000


def test_from_env_requires_a_token_and_applies_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PAGEHOST_TOKEN", raising=False)
    with pytest.raises(ValueError, match="PAGEHOST_TOKEN"):
        Settings.from_env({})

    settings = Settings.from_env(
        {
            "PAGEHOST_TOKEN": "dev-token",
            "PAGEHOST_DATA_DIR": str(tmp_path),
            "PAGEHOST_MCP_AUTHOR": "ada",
        }
    )

    assert settings.token == "dev-token"
    assert settings.data_dir == tmp_path
    assert settings.mcp_author == "ada"
    assert settings.url_template == "https://{id}.pages.internal.example.com/"
    assert settings.default_format == "markdown"
    assert settings.max_source_bytes == 1_000_000
    assert settings.full_read_tokens == 1000


def test_url_template_must_contain_the_id_placeholder(tmp_path: Path):
    with pytest.raises(ValueError, match="{id}"):
        Settings(data_dir=tmp_path, token="t", url_template="https://pages.example/")
