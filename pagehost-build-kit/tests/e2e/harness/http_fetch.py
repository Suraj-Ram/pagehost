"""Fetch a page the way a browser would: GET its URL."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .runner import PageNotServed


class HttpFetcher:
    """``origin`` lets a test machine reach pages whose hostnames it cannot resolve (e.g. one
    nginx with wildcard subdomains): the request goes to ``origin`` with the page's Host header."""

    def __init__(self, origin: str | None = None, timeout: float = 15.0) -> None:
        self._origin, self._timeout = origin, timeout

    def __call__(self, url: str) -> str:
        parts = urlparse(url)
        if self._origin:
            target = self._origin.rstrip("/") + (parts.path or "/")
            headers = {"Host": parts.netloc}
        else:
            target, headers = url, {}
        r = httpx.get(target, headers=headers, follow_redirects=True, timeout=self._timeout)
        if r.status_code in (403, 404, 410):
            raise PageNotServed(url)
        r.raise_for_status()
        return r.text
