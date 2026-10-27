from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ReferenceCandidate


class ReferenceProvider(ABC):
    name = "base"
    description = ""
    terms_url: str | None = None

    @abstractmethod
    def search(self, query: str, limit: int = 10, **filters: Any) -> list[ReferenceCandidate]: ...

    @abstractmethod
    def get(self, provider_id: str, thumb_width: int | None = None) -> ReferenceCandidate:
        """Fetch one item; ``thumb_width`` asks for a larger thumbnail when the provider supports it."""

    def status(self) -> dict[str, Any]:
        return {"name": self.name, "available": True, "description": self.description, "terms": self.terms_url}
