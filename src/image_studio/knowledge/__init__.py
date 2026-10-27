"""Version-controlled visual knowledge base (markdown files under ``knowledge/``)."""

from .retrieval import search_knowledge
from .storage import KnowledgeEntry, KnowledgeStore

__all__ = ["KnowledgeEntry", "KnowledgeStore", "search_knowledge"]
