"""Stable error codes. Field names and codes are the contract; message text is not."""

from __future__ import annotations

from typing import Any


class PagehostError(Exception):
    code = "internal_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = {
            key: value
            for key, value in details.items()
            if value is not None and value != [] and value != ""
        }

    def as_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return body


class InvalidPageId(PagehostError):
    code = "invalid_page_id"


class PageNotFound(PagehostError):
    code = "page_not_found"


class VersionNotFound(PagehostError):
    code = "version_not_found"


class SectionNotFound(PagehostError):
    code = "section_not_found"


class PageExists(PagehostError):
    code = "page_exists"


class VersionConflict(PagehostError):
    code = "version_conflict"


class EditConflict(PagehostError):
    code = "edit_conflict"


class InvalidContent(PagehostError):
    code = "invalid_content"


class ContentTooLarge(PagehostError):
    code = "content_too_large"


class UnknownFormat(PagehostError):
    code = "unknown_format"


class UnsupportedOperation(PagehostError):
    code = "unsupported_operation"


class Unauthorized(PagehostError):
    code = "unauthorized"
