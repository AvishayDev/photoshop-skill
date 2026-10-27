"""Search a local folder of images the user owns (filename/keyword match)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ...core.provenance import LicenseInfo
from ...errors import NotFoundError
from ...security import resolve_read_path
from ..models import ReferenceCandidate
from .base import ReferenceProvider

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


class LocalFolderProvider(ReferenceProvider):
    name = "local"
    description = "Images in folders listed in IMAGE_STUDIO_REFERENCE_DIRS (user-owned material)"

    def __init__(self, folders: list[Path] | None = None):
        if folders is None:
            raw = os.environ.get("IMAGE_STUDIO_REFERENCE_DIRS", "")
            folders = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
        self.folders = folders

    def status(self) -> dict[str, Any]:
        return {**super().status(), "available": bool(self.folders), "folders": [str(f) for f in self.folders]}

    def search(self, query: str, limit: int = 10, **filters: Any) -> list[ReferenceCandidate]:
        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 1]
        hits = []
        for folder in self.folders:
            root = resolve_read_path(folder)
            for p in root.rglob("*"):
                if p.suffix.lower() not in EXTS:
                    continue
                name = p.stem.lower().replace("_", " ").replace("-", " ")
                score = sum(t in name or t in str(p.parent).lower() for t in terms)
                if score:
                    hits.append((score, p))
        hits.sort(key=lambda h: (-h[0], str(h[1])))
        return [self._cand(p) for _, p in hits[:limit]]

    def get(self, provider_id: str, thumb_width: int | None = None) -> ReferenceCandidate:
        p = resolve_read_path(provider_id)
        if not p.is_file():
            raise NotFoundError(provider_id)
        return self._cand(p)

    def _cand(self, p: Path) -> ReferenceCandidate:
        return ReferenceCandidate(provider=self.name, provider_id=str(p), title=p.stem, image_url=None,
                                  license=LicenseInfo(short_name="User-provided",
                                                      notes="Local file; the user is responsible for its rights"))
