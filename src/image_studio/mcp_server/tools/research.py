from __future__ import annotations

from typing import Any

from ...knowledge.retrieval import search_knowledge as _search_kb
from ...research.reference_analysis import analyze_references
from .common import DocId


def register(tool, session) -> None:
    rs = session.research
    kb = session.knowledge

    @tool(read_only=True, title="Search knowledge base")
    def search_knowledge(query: str, limit: int = 8, category: str | None = None) -> dict[str, Any]:
        """Search the persistent, version-controlled visual knowledge base (subjects, environments, materials,
        lighting, techniques) BEFORE doing new research. Reuse what is relevant; research what is missing."""
        return _search_kb(query, limit, kb, category)

    @tool(read_only=True, title="Read knowledge entry")
    def read_knowledge(path: str) -> dict[str, Any]:
        """Read a knowledge entry by path (e.g. 'subjects/animals/tiger'): front matter, sections, sources."""
        e = kb.read(path)
        return {"ok": True, "path": e.path, "title": e.title, "category": e.category, "tags": e.tags,
                "confidence": e.confidence, "reviewed": e.reviewed,
                "sources": [s.model_dump() for s in e.sources], "related": e.related, "sections": e.sections()}

    @tool(title="Save knowledge")
    def save_knowledge(path: str, sections: dict[str, str], title: str | None = None,
                       category: str | None = None, tags: list[str] | None = None, aliases: list[str] | None = None,
                       confidence: str | None = None, sources: list[dict[str, Any]] | None = None,
                       related: list[str] | None = None, mode: str = "append") -> dict[str, Any]:
        """Create or extend a knowledge entry with GENUINELY REUSABLE lessons (not task noise). sections maps
        headings ('Visual observations', 'Editing recipe', 'Failure modes', 'Parameters', 'Limitations',
        'Examples') to concise markdown in your own words. sources: [{url, title, license, supports: [...]}].
        Unsupported claims must use confidence 'low'. Never paste copyrighted articles or embed images.
        The entry is a file in the repository - remind the user to commit it."""
        return kb.upsert(path, title=title, category=category, tags=tags, aliases=aliases, confidence=confidence,
                         sources=sources, related=related, sections=sections, mode=mode)

    @tool(read_only=True, open_world=True, title="Search reference images")
    def search_references(query: str, providers: list[str] | None = None, limit: int = 8,
                          reusable_only: bool = False, commercial: bool = False) -> dict[str, Any]:
        """Search free reference-image providers (wikimedia_commons, openverse, local folders) with license
        metadata and a reuse assessment for each hit. Use several specific queries per aspect (anatomy,
        texture, lighting, environment interaction). Results are candidates: fetch and LOOK at them."""
        return rs.search(query, providers, limit, reusable_only, commercial)

    @tool(read_only=True, open_world=True, title="Reference metadata")
    def get_reference_metadata(reference_key: str) -> dict[str, Any]:
        """Full metadata (source page, author, license, description) for a search hit ('provider:id')."""
        from ...research.licensing import assess_reuse
        prov, pid = reference_key.split(":", 1)
        cand = rs.provider(prov).get(pid)
        return {"ok": True, **cand.model_dump(mode="json"), "reuse": assess_reuse(cand.license)}

    @tool(open_world=True, title="Fetch reference")
    def fetch_reference(document_id: DocId, reference_key: str, size: str = "thumbnail",
                        purpose: str = "study") -> dict[str, Any]:
        """Download a reference into the project's references/ with a provenance record. purpose='study'
        (size='thumbnail'; for learning visual characteristics) or 'composite' (size='large' ~2048 px, or
        'full' original; only if the license allows modification - the image becomes part of the artwork
        and needs attribution)."""
        return rs.fetch_reference(session.editor.project(document_id), reference_key, size, purpose)

    @tool(read_only=True, title="Analyze references")
    def analyze_visual_references(document_id: DocId, reference_ids: list[str]) -> dict[str, Any]:
        """Measure fetched references (palette, tonal range, warmth, sharpness, light gradient) and build a
        contact sheet image. View the contact sheet, then record_observation for each useful finding."""
        return analyze_references(session.editor.project(document_id), reference_ids)

    @tool(title="Record observation")
    def record_observation(document_id: DocId, aspect: str, observation: str, reference_ids: list[str],
                           confidence: str = "medium", subject: str | None = None) -> dict[str, Any]:
        """Record what you learned from references (aspect e.g. 'anatomy', 'stripe pattern', 'light through
        canopy'), citing the reference ids that support it. Observations without references are marked
        unsupported. Note uncertainty or conflicting evidence explicitly."""
        return rs.record_observation(session.editor.project(document_id), aspect, observation, reference_ids,
                                     confidence, subject)

    @tool(read_only=True, title="Research summary")
    def get_research_summary(document_id: DocId) -> dict[str, Any]:
        """All references (with licenses/roles) and observations for this project, grouped by aspect."""
        return rs.research_summary(session.editor.project(document_id))
