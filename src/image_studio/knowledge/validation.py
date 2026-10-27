"""Quality gates for knowledge entries (run on every write and by `image-studio kb validate`)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .storage import KnowledgeEntry

MAX_BODY_CHARS = 40_000
MAX_QUOTE_LINES = 12


def validate_entry(e: KnowledgeEntry) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def err(msg):
        out.append({"level": "error", "message": msg})

    def warn(msg):
        out.append({"level": "warning", "message": msg})

    if not e.title.strip():
        err("title is empty")
    if e.confidence not in ("low", "medium", "high"):
        err("confidence must be low, medium or high")
    try:
        dt.date.fromisoformat(e.reviewed[:10])
    except ValueError:
        err("reviewed must be an ISO date (YYYY-MM-DD)")
    if len(e.body) > MAX_BODY_CHARS:
        err(f"body exceeds {MAX_BODY_CHARS} characters; keep entries focused and summarized")
    if re.search(r"data:image/[a-z]+;base64,", e.body):
        err("embedded images are not allowed; link to sources instead")
    quote_lines = sum(1 for line in e.body.splitlines() if line.startswith(">"))
    if quote_lines > MAX_QUOTE_LINES:
        err("too much quoted text; summarize observations in your own words instead of copying articles")
    for s in e.sources:
        if not re.match(r"^https?://", s.url):
            err(f"source url must be http(s): {s.url}")
    if e.confidence == "high" and not e.sources:
        err("high confidence requires at least one source")
    if not e.sources:
        warn("no sources: mark claims as general practice and keep confidence low/medium")
    if "##" not in e.body:
        warn("body has no sections; use the standard headings (Visual observations, Editing recipe, ...)")
    if not e.tags:
        warn("no tags; add tags so retrieval can find this entry")
    return out
