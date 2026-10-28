"""Slug, page id, and input normalisation. SPEC §3.2 and §3.3."""

from __future__ import annotations

import re

import pytest

from pagehost.domain.errors import ContentTooLarge, InvalidContent, PageExists
from pagehost.domain.ids import allocate_page_id, is_valid_page_id, slug_title
from pagehost.domain.normalize import ensure_source_size, normalize_newlines, normalize_title

_HEX_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,55}-[0-9a-f]{6}$")


@pytest.mark.parametrize(
    "page_id",
    [
        "abc",
        "a-b",
        "aa-",
        "9ab",
        "page-abc123",
        "a" * 63,
        "a" + "-" * 62,
    ],
)
def test_page_id_pattern_accepts_safe_ids(page_id: str):
    assert is_valid_page_id(page_id)


@pytest.mark.parametrize(
    "page_id",
    [
        "",
        "a",
        "ab",
        "-ab",
        "Abc",
        "ABC",
        "a_b",
        "a.b",
        "a b",
        "ab/cd",
        "_assets",
        "a" * 64,
        "a" + "-" * 63,
    ],
)
def test_page_id_pattern_rejects_unsafe_ids(page_id: str):
    assert not is_valid_page_id(page_id)


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Hello World", "hello-world"),
        ("Hello, World!", "hello-world"),
        ("  Hello   World  ", "hello-world"),
        ("Hello---World", "hello-world"),
        ("hello_world", "hello-world"),
        ("2 Fast 2 Furious", "2-fast-2-furious"),
        ("Café", "caf"),
        ("a" * 50, "a" * 40),
        ("a" * 39 + "!!!" + "b", "a" * 39),
        (
            "The Quick Brown Fox Jumps Over The Lazy Dog",
            "the-quick-brown-fox-jumps-over-the-lazy",
        ),
        ("", "page"),
        ("   ", "page"),
        ("---", "page"),
        ("!!!", "page"),
        ("你好", "page"),
    ],
)
def test_slug_title_collapses_and_falls_back_to_page(title: str, slug: str):
    assert slug_title(title) == slug


def test_normalize_title_trims_and_enforces_length():
    assert normalize_title("  Hello  ") == "Hello"
    assert normalize_title("\n\tHello\r\n") == "Hello"
    assert normalize_title("a" * 200) == "a" * 200
    assert normalize_title("  " + "a" * 200 + "  ") == "a" * 200

    with pytest.raises(InvalidContent) as empty:
        normalize_title("   ")
    assert empty.value.code == "invalid_content"

    with pytest.raises(InvalidContent):
        normalize_title("")

    with pytest.raises(InvalidContent) as too_long:
        normalize_title("a" * 201)
    assert too_long.value.code == "invalid_content"

    with pytest.raises(InvalidContent):
        normalize_title("  " + "a" * 201 + "\n")


def test_normalize_newlines_converts_crlf_and_lone_cr():
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"
    assert normalize_newlines("a\r\n\r\nb") == "a\n\nb"
    assert normalize_newlines("a\r\rb") == "a\n\nb"
    assert normalize_newlines("\r\n") == "\n"
    assert normalize_newlines("\r") == "\n"
    assert "\r" not in normalize_newlines("left\r\nmiddle\rright\n")


def test_ensure_source_size_counts_utf8_bytes():
    assert ensure_source_size("abcd", 4) == 4
    assert ensure_source_size("é", 2) == 2
    assert ensure_source_size("", 0) == 0

    with pytest.raises(ContentTooLarge) as too_big:
        ensure_source_size("é", 1)
    assert too_big.value.code == "content_too_large"

    with pytest.raises(ContentTooLarge):
        ensure_source_size("abc", 2)


def test_allocate_page_id_appends_random_lowercase_hex():
    first = allocate_page_id("Hello, World!", lambda _page_id: False)
    second = allocate_page_id("Hello, World!", lambda _page_id: False)
    empty = allocate_page_id("!!!", lambda _page_id: False)

    assert re.fullmatch(r"hello-world-[0-9a-f]{6}", first)
    assert re.fullmatch(r"page-[0-9a-f]{6}", empty)
    assert first != second
    assert is_valid_page_id(first)
    assert is_valid_page_id(empty)
    assert _HEX_ID.fullmatch(first)


def test_allocate_page_id_gives_up_after_five_collisions():
    attempts: list[str] = []

    def taken(page_id: str) -> bool:
        attempts.append(page_id)
        return True

    with pytest.raises(PageExists) as raised:
        allocate_page_id("Hello", taken)

    assert raised.value.code == "page_exists"
    assert len(attempts) == 5
    assert len(set(attempts)) == 5
    assert all(re.fullmatch(r"hello-[0-9a-f]{6}", page_id) for page_id in attempts)


def test_allocate_page_id_returns_the_fifth_candidate_when_it_is_free():
    attempts: list[str] = []

    def taken(page_id: str) -> bool:
        attempts.append(page_id)
        return len(attempts) < 5

    page_id = allocate_page_id("Hello", taken)

    assert len(attempts) == 5
    assert page_id == attempts[-1]
    assert is_valid_page_id(page_id)
