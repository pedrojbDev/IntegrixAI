from __future__ import annotations


class BusinessRuleError(Exception):
    """Raised for recoverable business-validation errors returned by upstream."""

    def __init__(
        self,
        code: str,
        message: str,
        field: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}
