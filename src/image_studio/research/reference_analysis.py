"""Objective analysis of reference images + contact sheets for the agent's own visual inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..core.project import Project
from ..errors import NotFoundError, ValidationError
from ..security import safe_child
from ..workflows.quality_check import dominant_colors, image_stats, light_direction


def _load_ref(project: Project, ref_id: str) -> tuple[dict[str, Any], np.ndarray]:
    rec_path = safe_child(project.root / "references", f"{ref_id}.json")
    if not rec_path.exists():
        raise NotFoundError(f"Reference '{ref_id}' not found in this project")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    with Image.open(safe_child(project.root, *Path(rec["local_path"]).parts)) as im:
        arr = np.asarray(im.convert("RGBA")).copy()
    return rec, arr


def analyze_references(project: Project, reference_ids: list[str]) -> dict[str, Any]:
    """Measure palette, tonal range, contrast, warmth, sharpness and global light gradient of each reference,
    plus a cross-reference summary (consensus palette / spread). Write a contact sheet to inspect visually."""
    if not reference_ids:
        raise ValidationError("reference_ids must not be empty")
    per = []
    arrays = []
    for rid in reference_ids:
        rec, arr = _load_ref(project, rid)
        arrays.append((rid, rec, arr))
        st = image_stats(arr)
        per.append({"reference_id": rid, "title": rec.get("title"), "stats": st, "palette": dominant_colors(arr, 5),
                    "light": light_direction(arr), "license": (rec.get("license") or {}).get("short_name")})
    lum = [p["stats"]["mean_luminance"] for p in per]
    warm = [p["stats"]["warmth_b"] for p in per]
    summary = {"count": len(per), "mean_luminance_range": [min(lum), max(lum)], "warmth_b_range": [min(warm), max(warm)],
               "consistent_lighting": (max(lum) - min(lum)) < 0.2,
               "note": "Numbers describe tone/color only. Study the contact sheet for shape, anatomy, texture and "
                       "material cues, and record observations citing reference ids."}
    sheet = contact_sheet(project, arrays)
    return {"ok": True, "references": per, "summary": summary, "contact_sheet": str(sheet)}


def contact_sheet(project: Project, items: list[tuple[str, dict, np.ndarray]], cell: int = 320) -> Path:
    cols = min(4, len(items))
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 28)), (32, 32, 32))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, (rid, rec, arr) in enumerate(items):
        im = Image.fromarray(arr, "RGBA").convert("RGB")
        im.thumbnail((cell - 8, cell - 8))
        x, y = (i % cols) * cell, (i // cols) * (cell + 28)
        sheet.paste(im, (x + (cell - im.width) // 2, y + 4))
        label = f"{rid} {(rec.get('title') or '')[:34]}"
        draw.text((x + 6, y + cell + 6), label, fill=(230, 230, 230), font=font)
    out = project.root / "research" / f"contact_sheet_{'_'.join(r for r, _, _ in items)[:80]}.png"
    sheet.save(out)
    return out
