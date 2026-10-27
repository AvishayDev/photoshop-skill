"""Knowledge entries: markdown with YAML front matter, stored in the repository.

Entry layout::

    ---
    title: Tiger
    category: subjects/animals
    tags: [tiger, big cat, stripes, fur]
    aliases: [Panthera tigris]
    confidence: medium            # low | medium | high
    reviewed: 2026-10-27
    sources:
      - url: https://commons.wikimedia.org/wiki/File:...
        title: ...
        license: CC BY-SA 4.0
        supports: [stripes, anatomy]
    related: [materials/fur, environments/forest]
    ---
    ## Visual observations
    ## Editing recipe
    ## Failure modes
    ## Parameters
    ## Limitations
    ## Examples

Git history is the persistence layer: entries are plain files that anyone who
clones the repository can read, review and improve.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..config import get_settings
from ..errors import NotFoundError, ValidationError

FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
SECTIONS = ["Visual observations", "Editing recipe", "Failure modes", "Parameters", "Limitations", "Examples"]
_SAFE_PATH = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*){0,3}$")


class Source(BaseModel):
    url: str
    title: str | None = None
    license: str | None = None
    supports: list[str] = Field(default_factory=list)


class KnowledgeEntry(BaseModel):
    path: str  # relative, without .md, e.g. subjects/animals/tiger
    title: str
    category: str
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    reviewed: str = Field(default_factory=lambda: dt.date.today().isoformat())
    sources: list[Source] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    body: str = ""

    def to_markdown(self) -> str:
        fm = {"title": self.title, "category": self.category, "tags": self.tags, "aliases": self.aliases,
              "confidence": self.confidence, "reviewed": self.reviewed,
              "sources": [s.model_dump(exclude_none=True) for s in self.sources], "related": self.related}
        return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=110) + "---\n\n" + \
            self.body.strip() + "\n"

    def sections(self) -> dict[str, str]:
        out: dict[str, str] = {}
        current = "_intro"
        for line in self.body.splitlines():
            m = re.match(r"^##\s+(.*)$", line)
            if m:
                current = m.group(1).strip()
                out.setdefault(current, "")
                continue
            out[current] = out.get(current, "") + line + "\n"
        return {k: v.strip() for k, v in out.items()}


def parse_entry(text: str, rel: str) -> KnowledgeEntry:
    m = FRONT.match(text)
    if not m:
        raise ValidationError(f"{rel}: missing YAML front matter")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"{rel}: invalid YAML front matter: {exc}") from exc
    if isinstance(fm.get("reviewed"), (dt.date, dt.datetime)):
        fm["reviewed"] = fm["reviewed"].isoformat()[:10]
    fm.setdefault("category", rel.rsplit("/", 1)[0] if "/" in rel else "general")
    return KnowledgeEntry(path=rel, body=m.group(2), **fm)


class KnowledgeStore:
    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().knowledge_dir).resolve()

    def _file(self, rel: str) -> Path:
        rel = rel.removesuffix(".md").strip("/")
        if not _SAFE_PATH.match(rel):
            raise ValidationError("Knowledge paths look like 'subjects/animals/tiger' (lowercase, a-z0-9_-)")
        return self.root / f"{rel}.md"

    def all(self) -> list[KnowledgeEntry]:
        out = []
        for p in sorted(self.root.rglob("*.md")):
            if p.name.lower() in ("readme.md", "index.md") or p.name.startswith("_"):
                continue
            rel = p.relative_to(self.root).with_suffix("").as_posix()
            try:
                out.append(parse_entry(p.read_text(encoding="utf-8"), rel))
            except ValidationError:
                continue
        return out

    def read(self, rel: str) -> KnowledgeEntry:
        p = self._file(rel)
        if not p.exists():
            raise NotFoundError(f"No knowledge entry '{rel}'", hint="Use search_knowledge to find entries")
        return parse_entry(p.read_text(encoding="utf-8"), rel.removesuffix(".md"))

    def exists(self, rel: str) -> bool:
        return self._file(rel).exists()

    def write(self, entry: KnowledgeEntry) -> Path:
        from .validation import validate_entry
        problems = validate_entry(entry)
        errors = [p for p in problems if p["level"] == "error"]
        if errors:
            raise ValidationError("Knowledge entry rejected: " + "; ".join(p["message"] for p in errors),
                                  details={"problems": problems})
        p = self._file(entry.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".md.tmp")
        tmp.write_text(entry.to_markdown(), encoding="utf-8")
        tmp.replace(p)
        return p

    def upsert(self, path: str, *, title: str | None = None, category: str | None = None,
               tags: list[str] | None = None, aliases: list[str] | None = None, confidence: str | None = None,
               sources: list[dict[str, Any]] | None = None, related: list[str] | None = None,
               sections: dict[str, str] | None = None, mode: str = "append") -> dict[str, Any]:
        """Create an entry or merge new knowledge into it. ``sections`` maps a section heading (e.g.
        'Visual observations') to markdown text; mode 'append' adds to existing sections, 'replace' overwrites."""
        rel = path.removesuffix(".md")
        created = not self.exists(rel)
        if created:
            if not title:
                raise ValidationError("title is required for a new entry")
            entry = KnowledgeEntry(path=rel, title=title, category=category or rel.rsplit("/", 1)[0])
        else:
            entry = self.read(rel)
        if title:
            entry.title = title
        if category:
            entry.category = category
        for attr, vals in (("tags", tags), ("aliases", aliases), ("related", related)):
            if vals:
                merged = list(dict.fromkeys([*getattr(entry, attr), *[v.strip() for v in vals if v.strip()]]))
                setattr(entry, attr, merged)
        if confidence:
            entry.confidence = confidence
        if sources:
            known = {s.url for s in entry.sources}
            for s in sources:
                src = Source(**s)
                if src.url not in known:
                    entry.sources.append(src)
                    known.add(src.url)
        if sections:
            existing = entry.sections()
            for heading, text in sections.items():
                text = text.strip()
                if not text:
                    continue
                if mode == "append" and existing.get(heading):
                    if text in existing[heading]:
                        continue
                    existing[heading] = existing[heading] + "\n" + text
                else:
                    existing[heading] = text
            intro = existing.pop("_intro", "")
            order = [h for h in SECTIONS if h in existing] + [h for h in existing if h not in SECTIONS]
            entry.body = (intro + "\n\n" if intro else "") + "\n\n".join(f"## {h}\n\n{existing[h]}" for h in order)
        entry.reviewed = dt.date.today().isoformat()
        p = self.write(entry)
        from .validation import validate_entry
        return {"ok": True, "created": created, "path": str(p), "entry": entry.path,
                "warnings": [w["message"] for w in validate_entry(entry) if w["level"] == "warning"],
                "hint": "Commit the change with git so the knowledge persists for everyone."}
