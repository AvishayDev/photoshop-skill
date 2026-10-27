from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.provenance import LicenseInfo


class ReferenceCandidate(BaseModel):
    """A search hit. Not downloaded yet; ``provider_id`` lets ``fetch_reference`` retrieve it."""

    provider: str
    provider_id: str
    title: str
    source_page: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    width: int | None = None
    height: int | None = None
    mime: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    license: LicenseInfo | None = None
    reuse: dict[str, Any] | None = None  # filled by licensing.assess_reuse

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.provider_id}"
