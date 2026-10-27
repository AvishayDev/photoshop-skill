"""Wikimedia Commons via the MediaWiki Action API (no API key required).

API: https://commons.wikimedia.org/w/api.php (generator=search over the File
namespace, prop=imageinfo with extmetadata for license/author/credit).
Etiquette (https://meta.wikimedia.org/wiki/User-Agent_policy, API etiquette):
descriptive User-Agent with contact URL, serial requests, ``maxlag``, and
backing off on 429/503. Thumbnails are requested at modest widths.
"""

from __future__ import annotations

import html
import re
from typing import Any

from ...core.provenance import LicenseInfo
from ...errors import NotFoundError, ResearchError
from ..http import PoliteClient
from ..models import ReferenceCandidate
from .base import ReferenceProvider

API = "https://commons.wikimedia.org/w/api.php"
_TAG = re.compile(r"<[^>]+>")
EXT_FIELDS = ("LicenseShortName|LicenseUrl|Artist|Credit|AttributionRequired|UsageTerms|ImageDescription|"
              "Copyrighted|DateTimeOriginal|Restrictions")


def strip_html(value: str | None, limit: int = 600) -> str | None:
    if not value:
        return None
    text = html.unescape(_TAG.sub("", value)).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit] or None


class WikimediaCommonsProvider(ReferenceProvider):
    name = "wikimedia_commons"
    description = "Wikimedia Commons: freely licensed media with structured license metadata"
    terms_url = "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"

    def __init__(self, client: PoliteClient | None = None, thumb_width: int = 640):
        self.client = client or PoliteClient(min_interval=1.0)
        self.thumb_width = thumb_width

    def _params(self, thumb_width: int | None = None, **extra: Any) -> dict[str, Any]:
        return {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5",
                "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": str(thumb_width or self.thumb_width), "iiextmetadatafilter": EXT_FIELDS, **extra}

    def search(self, query: str, limit: int = 10, **filters: Any) -> list[ReferenceCandidate]:
        q = query.strip()
        if not q:
            raise ResearchError("Empty query")
        search = f"filetype:bitmap {q}"
        data = self.client.get_json(API, self._params(generator="search", gsrsearch=search, gsrnamespace="6",
                                                      gsrlimit=str(max(1, min(limit, 50)))))
        if "error" in data:
            raise ResearchError(f"Wikimedia API error: {data['error'].get('info')}")
        pages = (data.get("query") or {}).get("pages") or []
        pages.sort(key=lambda p: p.get("index", 0))
        return [c for c in (self._to_candidate(p) for p in pages) if c is not None]

    def get(self, provider_id: str, thumb_width: int | None = None) -> ReferenceCandidate:
        if not provider_id.isdigit():
            raise ResearchError("Wikimedia ids are numeric page ids")
        data = self.client.get_json(API, self._params(thumb_width, pageids=provider_id))
        pages = (data.get("query") or {}).get("pages") or []
        if not pages or pages[0].get("missing"):
            raise NotFoundError(f"Wikimedia page {provider_id} not found")
        cand = self._to_candidate(pages[0])
        if cand is None:
            raise NotFoundError(f"Wikimedia page {provider_id} has no image info")
        return cand

    def _to_candidate(self, page: dict[str, Any]) -> ReferenceCandidate | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        ii = infos[0]
        meta = {k: (v or {}).get("value") for k, v in (ii.get("extmetadata") or {}).items()}
        attribution_required = None
        if meta.get("AttributionRequired") is not None:
            attribution_required = str(meta["AttributionRequired"]).lower() == "true"
        lic = LicenseInfo(short_name=strip_html(meta.get("LicenseShortName")), url=meta.get("LicenseUrl"),
                          author=strip_html(meta.get("Artist"), 200), credit=strip_html(meta.get("Credit"), 300),
                          attribution_required=attribution_required, usage_terms=strip_html(meta.get("UsageTerms")),
                          source_page=ii.get("descriptionurl"),
                          notes=strip_html(meta.get("Restrictions"), 200))
        title = page.get("title", "").removeprefix("File:")
        return ReferenceCandidate(provider=self.name, provider_id=str(page.get("pageid")), title=title,
                                  source_page=ii.get("descriptionurl"), image_url=ii.get("url"),
                                  thumbnail_url=ii.get("thumburl"), width=ii.get("width"), height=ii.get("height"),
                                  mime=ii.get("mime"), description=strip_html(meta.get("ImageDescription")),
                                  license=lic)
