"""Error types with stable codes and recovery hints.

Every error raised to an agent carries a machine-readable ``code`` and a human
``hint`` so the agent can decide how to recover instead of guessing.
"""

from __future__ import annotations

from typing import Any


class StudioError(Exception):
    code = "studio_error"

    def __init__(self, message: str, *, hint: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": {"code": self.code, "message": self.message}}
        if self.hint:
            out["error"]["hint"] = self.hint
        if self.details:
            out["error"]["details"] = self.details
        return out


class ValidationError(StudioError):
    code = "invalid_parameter"


class NotFoundError(StudioError):
    code = "not_found"


class UnsupportedOperationError(StudioError):
    code = "unsupported_operation"


class BackendUnavailableError(StudioError):
    code = "backend_unavailable"


class BackendExecutionError(StudioError):
    code = "backend_failed"


class PathSecurityError(StudioError):
    code = "path_not_allowed"


class PlanRequiredError(StudioError):
    code = "plan_required"


class ResearchError(StudioError):
    code = "research_failed"


class ProviderUnavailableError(StudioError):
    code = "provider_unavailable"
