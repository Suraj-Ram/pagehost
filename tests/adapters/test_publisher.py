import os
from pathlib import Path

import pytest

from pagehost.adapters.publisher import FilesystemPublisher
from pagehost.adapters.url_scheme import TemplateUrlScheme


def test_publish_is_readable_through_current(tmp_path: Path):
    publisher = FilesystemPublisher(tmp_path)

    publisher.publish("alpha", 1, "<p>one</p>")

    current = tmp_path / "alpha" / "current"
    assert os.readlink(current) == "v1"
    assert (current / "index.html").read_text(encoding="utf-8") == "<p>one</p>"
    assert {path.name for path in (tmp_path / "alpha" / "v1").iterdir()} == {"index.html"}


def test_second_publish_swaps_the_current_target(tmp_path: Path):
    publisher = FilesystemPublisher(tmp_path)
    publisher.publish("alpha", 1, "<p>one</p>")

    publisher.publish("alpha", 2, "<p>two</p>")

    current = tmp_path / "alpha" / "current"
    assert os.readlink(current) == "v2"
    assert (current / "index.html").read_text(encoding="utf-8") == "<p>two</p>"
    assert (tmp_path / "alpha" / "v1" / "index.html").read_text(encoding="utf-8") == "<p>one</p>"


def test_publish_is_idempotent(tmp_path: Path):
    publisher = FilesystemPublisher(tmp_path)
    publisher.publish("alpha", 1, "<p>one</p>")

    publisher.publish("alpha", 1, "<p>one</p>")

    current = tmp_path / "alpha" / "current"
    assert os.readlink(current) == "v1"
    assert (current / "index.html").read_text(encoding="utf-8") == "<p>one</p>"
    assert {path.name for path in (tmp_path / "alpha").iterdir()} == {"v1", "current"}


def test_unpublish_removes_only_the_current_pointer(tmp_path: Path):
    publisher = FilesystemPublisher(tmp_path)
    publisher.publish("alpha", 1, "<p>one</p>")
    publisher.publish("alpha", 2, "<p>two</p>")
    publisher.install_assets({"pagehost.css": b"body{}"})

    publisher.unpublish("alpha")

    assert not os.path.lexists(tmp_path / "alpha" / "current")
    assert (tmp_path / "alpha" / "v1" / "index.html").read_text(encoding="utf-8") == "<p>one</p>"
    assert (tmp_path / "alpha" / "v2" / "index.html").read_text(encoding="utf-8") == "<p>two</p>"
    assert (tmp_path / "_assets" / "pagehost.css").read_bytes() == b"body{}"
    publisher.unpublish("alpha")
    publisher.unpublish("missing")


@pytest.mark.parametrize(
    "name",
    ["", ".hidden", ".", "..", "../escape", "dir/file.css", "dir\\file.css", "/absolute.css"],
)
def test_install_assets_rejects_unsafe_names(tmp_path: Path, name: str):
    publisher = FilesystemPublisher(tmp_path)

    with pytest.raises(ValueError):
        publisher.install_assets({name: b"nope", "pagehost.css": b"ok"})

    assert list(tmp_path.rglob("*")) == []


def test_install_assets_writes_each_name_under_assets(tmp_path: Path):
    publisher = FilesystemPublisher(tmp_path)

    publisher.install_assets({"pagehost.css": b"body{}", "mark.bin": b"\xff"})
    publisher.install_assets({"pagehost.css": b"updated"})

    assert (tmp_path / "_assets" / "pagehost.css").read_bytes() == b"updated"
    assert (tmp_path / "_assets" / "mark.bin").read_bytes() == b"\xff"


@pytest.mark.parametrize(
    ("template", "page_id", "url"),
    [
        (
            "https://{id}.pages.internal.example.com/",
            "alpha",
            "https://alpha.pages.internal.example.com/",
        ),
        (
            "https://pages.example.com/p/{id}/",
            "alpha",
            "https://pages.example.com/p/alpha/",
        ),
    ],
)
def test_url_for_substitutes_the_id(template: str, page_id: str, url: str):
    assert TemplateUrlScheme(template).url_for(page_id) == url


def test_url_template_must_contain_the_id_placeholder():
    with pytest.raises(ValueError, match="{id}"):
        TemplateUrlScheme("https://pages.example.com/")
