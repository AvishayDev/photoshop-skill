"""Openverse (https://openverse.org) image search API.

Endpoint: GET https://api.openverse.org/v1/images/?q=...  (anonymous access is
allowed with lower rate limits; set IMAGE_STUDIO_OPENVERSE_TOKEN to use an
OAuth access token for higher limits). Results aggregate openly licensed
images (Flickr, museums, Wikimedia, ...) with license and attribution fields.
"""

from __future__ import annotations

from typing import Any

from ...config import get_settings
from ...core.provenance import LicenseInfo
from ...errors import NotFoundError, ResearchError
from ..http import PoliteClient
from ..models import ReferenceCandidate
from .base import ReferenceProvider

API = "https://api.openverse.org/v1/images/"


class OpenverseProvider(ReferenceProvider):
    name = "openverse"
    description = "Openverse: search across openly licensed images from many institutions"
    terms_url = "https://docs.openverse.org/terms_of_service.html"

    def __init__(self, client: PoliteClient | None = None):
        self.client = client or PoliteClient(min_interval=1.5)

    def _headers(self) -> dict[str, str] | None:
        token = get_settings().openverse_token
        return {"Authorization": f"Bearer {token}"} if token else None

    def search(self, query: str, limit: int = 10, **filters: Any) -> list[ReferenceCandidate]:
        if not query.strip():
            raise ResearchError("Empty query")
        params: dict[str, Any] = {"q": query.strip(), "page_size": max(1, min(limit, 20)), "mature": "false"}
        if filters.get("commercial"):
            params["license_type"] = "commercial,modification" if filters.get("modification") else "commercial"
        elif filters.get("modification"):
            params["license_type"] = "modification"
        data = self.client.get_json(API, params, headers=self._headers())
        return [self._to_candidate(r) for r in data.get("results", [])]

    def get(self, provider_id: str, thumb_width: int | None = None) -> ReferenceCandidate:
        if not provider_id.replace("-", "").isalnum():
            raise ResearchError("Invalid Openverse id")
        data = self.client.get_json(f"{API}{provider_id}/", headers=self._headers())
        if not data or "id" not in data:
            raise NotFoundError(f"Openverse image {provider_id} not found")
        return self._to_candidate(data)

    def _to_candidate(self, r: dict[str, Any]) -> ReferenceCandidate:
        lic_code = (r.get("license") or "").lower()
        version = r.get("license_version") or ""
        if lic_code in ("cc0",):
            short = f"CC0 {version}".strip()
        elif lic_code == "pdm":
            short = "Public Domain Mark"
        else:
            short = f"CC {lic_code.upper()} {version}".strip() if lic_code else None
        lic = LicenseInfo(short_name=short, url=r.get("license_url"), author=r.get("creator"),
                          credit=r.get("attribution"), attribution_required=lic_code not in ("cc0", "pdm"),
                          source_page=r.get("foreign_landing_url"),
                          notes=f"via Openverse from {r.get('source') or r.get('provider')}")
        return ReferenceCandidate(provider=self.name, provider_id=str(r.get("id")), title=r.get("title") or "untitled",
                                  source_page=r.get("foreign_landing_url"), image_url=r.get("url"),
                                  thumbnail_url=r.get("thumbnail"), width=r.get("width"), height=r.get("height"),
                                  mime=f"image/{r['filetype']}" if r.get("filetype") else None,
                                  tags=[t.get("name") for t in r.get("tags") or [] if t.get("name")][:20],
                                  license=lic)
