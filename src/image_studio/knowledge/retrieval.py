"""Local lexical retrieval (BM25 with field boosts). No external services or embeddings required."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .storage import KnowledgeEntry, KnowledgeStore

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "is", "are", "be", "as", "at", "by",
         "it", "this", "that", "from", "into", "how", "what", "use"}


def tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if t in _STOP or len(t) < 2:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]  # crude plural folding: stripes -> stripe
        out.append(t)
    return out


def _doc_tokens(e: KnowledgeEntry) -> list[str]:
    boosted = (tokens(e.title) * 4 + tokens(" ".join(e.tags)) * 3 + tokens(" ".join(e.aliases)) * 3 +
               tokens(e.category.replace("/", " ")) * 2 +
               tokens(" ".join(re.findall(r"^#+\s+(.*)$", e.body, re.M))) * 2 + tokens(e.body))
    return boosted


def search_knowledge(query: str, limit: int = 8, store: KnowledgeStore | None = None,
                     category: str | None = None) -> dict[str, Any]:
    store = store or KnowledgeStore()
    entries = [e for e in store.all() if not category or e.category.startswith(category)]
    q = tokens(query)
    if not q or not entries:
        return {"ok": True, "query": query, "results": [], "total_entries": len(entries)}
    docs = [_doc_tokens(e) for e in entries]
    N = len(docs)
    avgdl = sum(len(d) for d in docs) / N
    df = Counter(t for d in docs for t in set(d))
    k1, b = 1.4, 0.75
    scored = []
    for e, d in zip(entries, docs):
        tf = Counter(d)
        s = 0.0
        for t in set(q):
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        if s > 0:
            scored.append((s, e))
    scored.sort(key=lambda x: -x[0])
    results = []
    for s, e in scored[:limit]:
        results.append({"path": e.path, "title": e.title, "category": e.category, "score": round(s, 3),
                        "confidence": e.confidence, "reviewed": e.reviewed, "tags": e.tags,
                        "snippet": _snippet(e.body, q), "sections": list(e.sections().keys())})
    return {"ok": True, "query": query, "results": results, "total_entries": N}


def _snippet(body: str, q: list[str], width: int = 260) -> str:
    low = body.lower()
    pos = min((low.find(t) for t in q if low.find(t) >= 0), default=0)
    start = max(0, pos - 60)
    text = re.sub(r"\s+", " ", body[start:start + width]).strip()
    return ("..." if start else "") + text + "..."
