"""Fill ``{id}`` into the configured page URL template."""

from __future__ import annotations


class TemplateUrlScheme:
    """UrlScheme backed by a template such as ``https://{id}.pages.example.com/``."""

    def __init__(self, template: str) -> None:
        if "{id}" not in template:
            raise ValueError("url_template must contain {id}")
        self._template = template

    def url_for(self, page_id: str) -> str:
        return self._template.replace("{id}", page_id)
