"""Pattern library: JSON entries under ``knowledge/patterns/<kind>/<slug>.json``.

Kinds:
    figure      a subject recipe for :func:`image_studio.paint.figure.render_figure` (parts, materials, details)
    texture     parameters for a pattern generator (stripes, spots, scales, bark, ...), usually measured
    palette     named colour sets with their share/role (base, marks, highlight, shadow)
    silhouette  a normalized outline contour learned from a reference (usable as a figure 'contour' part)
    scene       an environment recipe (pipeline steps/parameters for sky, forest, ocean, ...)
    light       a lighting setup (key/ambient colours, azimuth/elevation, haze) for a time of day/weather
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import get_settings
from ..errors import NotFoundError, ValidationError
from ..knowledge.retrieval import tokens
from ..knowledge.storage import Source

KINDS = ("figure", "texture", "palette", "silhouette", "scene", "light")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class PatternEntry(BaseModel):
    id: str = Field(description="'<kind>/<slug>', e.g. 'texture/tiger-stripes'")
    title: str
    kind: str
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict, description="What the painting engine consumes")
    learned: dict[str, Any] = Field(default_factory=dict, description="Raw measurements from references")
    sources: list[Source] = Field(default_factory=list)
    confidence: str = "medium"
    notes: str = ""
    used_in: list[str] = Field(default_factory=list, description="Pipelines/requests that used this entry")
    reviewed: str = Field(default_factory=lambda: dt.date.today().isoformat())

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "kind": self.kind, "tags": self.tags,
                "confidence": self.confidence, "reviewed": self.reviewed, "notes": self.notes[:200]}


class PatternLibrary:
    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().knowledge_dir / "patterns").resolve()

    def _file(self, pid: str) -> Path:
        kind, _, slug = pid.partition("/")
        if kind not in KINDS or not _SLUG.match(slug):
            raise ValidationError(f"Pattern ids look like '<kind>/<slug>' with kind in {list(KINDS)} and a "
                                  "lowercase slug (a-z, 0-9, '-')", details={"id": pid})
        return self.root / kind / f"{slug}.json"

    def all(self, kind: str | None = None) -> list[PatternEntry]:
        out = []
        if not self.root.exists():
            return out
        for p in sorted(self.root.rglob("*.json")):
            try:
                e = PatternEntry.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if kind is None or e.kind == kind:
                out.append(e)
        return out

    def get(self, pid: str) -> PatternEntry:
        p = self._file(pid)
        if not p.exists():
            raise NotFoundError(f"No pattern '{pid}'", hint="Use search_patterns to find entries")
        return PatternEntry.model_validate_json(p.read_text(encoding="utf-8"))

    def exists(self, pid: str) -> bool:
        return self._file(pid).exists()

    def save(self, entry: PatternEntry, overwrite: bool = True) -> Path:
        if entry.kind not in KINDS or not entry.id.startswith(entry.kind + "/"):
            raise ValidationError("entry.id must start with its kind, e.g. 'texture/tiger-stripes'")
        if entry.confidence not in ("low", "medium", "high"):
            raise ValidationError("confidence must be low, medium or high")
        if entry.confidence == "high" and not entry.sources:
            raise ValidationError("confidence 'high' requires at least one source")
        p = self._file(entry.id)
        if p.exists() and not overwrite:
            raise ValidationError(f"Pattern '{entry.id}' exists; pass overwrite=true to update it")
        p.parent.mkdir(parents=True, exist_ok=True)
        entry.reviewed = dt.date.today().isoformat()
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entry.model_dump(exclude_none=True), indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(p)
        return p

    def search(self, query: str, kind: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        q = set(tokens(query))
        scored = []
        for e in self.all(kind):
            title = set(tokens(e.title + " " + e.id.replace("-", " ").replace("/", " ")))
            tags = set(tokens(" ".join(e.tags + e.aliases)))
            body = set(tokens(e.notes))
            s = 3 * len(q & title) + 2 * len(q & tags) + len(q & body)
            if s:
                scored.append((s, e))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [{**e.summary(), "score": s} for s, e in scored[:limit]]
