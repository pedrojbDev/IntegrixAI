from __future__ import annotations


class BusinessRuleError(Exception):
    """Raised for recoverable business-validation errors returned by upstream."""

    def __init__(
        self,
        code: str,
        message: str,
        field: str | None = None,
        details: dict | None = None,
        retryable: bool = True,
        handoff_after_retry: bool = True,
        attempt: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}
        self.retryable = retryable
        self.handoff_after_retry = handoff_after_retry
        # Tenant policies may count real user turns instead of tool invocations.
        self.attempt = attempt
