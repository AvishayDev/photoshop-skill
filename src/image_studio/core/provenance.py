"""Source and licensing metadata attached to assets and references.

This lives in ``core`` (not ``research``) because every imported asset needs it,
whether it came from the web, a local folder or a generative model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LicenseInfo(BaseModel):
    short_name: str | None = Field(None, description="e.g. 'CC BY-SA 4.0', 'CC0', 'Public domain'")
    url: str | None = None
    author: str | None = None
    credit: str | None = None
    attribution_required: bool | None = None
    usage_terms: str | None = None
    source_page: str | None = None
    notes: str | None = None


class Provenance(BaseModel):
    origin: str = Field("unknown", description="local_file | web_reference | generated | procedural | derived")
    source_url: str | None = None
    original_path: str | None = None
    provider: str | None = None
    provider_id: str | None = None
    retrieved_at: str | None = None
    license: LicenseInfo | None = None
    generator: dict | None = None
