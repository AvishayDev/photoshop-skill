"""Painting from scratch, pipelines, pattern learning and the pattern library."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from pydantic import Field

from ...core.provenance import LicenseInfo
from ...errors import NotFoundError, ValidationError
from ...paint import canvas, synthesis
from ...patterns import PatternEntry, PatternLibrary, learn_from_image
from ...pipeline import Pipeline
from ...pipeline.spec import describe_actions, run_spec, run_step
from ...research.licensing import assess_reuse, attribution_line
from ...security import safe_child
from .common import DocId, Params, Points, Rect

PatternId = Annotated[str, Field(description="'<kind>/<slug>', e.g. 'figure/tiger-walking' or 'texture/tiger-stripes'")]


def _reference(proj, reference_id: str) -> tuple[dict[str, Any], np.ndarray]:
    from PIL import Image

    rec_path = safe_child(proj.root / "references", f"{reference_id}.json")
    if not rec_path.exists():
        raise NotFoundError(f"No downloaded reference '{reference_id}' in this project",
                            hint="search_references then fetch_reference first")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    with Image.open(safe_child(proj.root, *Path(rec["local_path"]).parts)) as im:
        return rec, np.asarray(im.convert("RGBA")).copy()


def register(tool, session) -> None:
    ed = session.editor
    lib = PatternLibrary()

    @tool(read_only=True, title="List painting actions")
    def list_paint_actions() -> dict[str, Any]:
        """Painting actions available to paint_layer and run_pipeline (sky, clouds, sun, mountains, ground,
        ocean, forest, foliage, grass, light_rays, haze, dapples, figure, pattern, strokes, shape, cast_shadow,
        contact_shadow, reflection, rim_light, adjust, vignette, grain, wash) with their parameters. These
        paint pixels from scratch - no photo and no generative model is needed."""
        return {"ok": True, "actions": describe_actions(),
                "conventions": "Canvas pixels, origin top-left, y down. Light azimuth = where light comes FROM "
                               "(0 right, 90 front, 180 left, 270 behind). Figure sizes are fractions of the "
                               "figure height. Each action creates one named layer (forest creates several)."}

    @tool(mutating=True, title="Paint a layer")
    def paint_layer(document_id: DocId, action: str, params: Params = None, name: str | None = None,
                    group: str | None = None, blend_mode: str = "normal", opacity: float = 1.0,
                    seed: int = 0) -> dict[str, Any]:
        """Paint one action (see list_paint_actions) into an existing document as new named layer(s).
        Subject-relative actions (cast_shadow, contact_shadow, reflection, rim_light, pattern with
        mask_layer) refer to other layers BY NAME, e.g. params={"of": "Tiger", "azimuth": 150, ...}.
        Example: action='figure', params={'spec': 'figure/tiger-walking', 'height': 330, 'x': 470,
        'ground_y': 880, 'facing': 'left', 'light_azimuth': 150}."""
        p = Pipeline.attach(document_id, ed, seed=seed)
        step = {"action": action, "name": name, "params": params or {}, "blend": blend_mode, "opacity": opacity}
        if group:
            step["group"] = group
        ids = run_step(p, step)
        return ed.result(ed.project(document_id), layer_ids=ids,
                         hint="render_preview and LOOK at the result before continuing")

    @tool(mutating=True, title="Run a painting pipeline")
    def run_pipeline(spec: Annotated[dict[str, Any], Field(description=(
            "{'request': str, 'plan': [>=10 steps], 'size': [w, h], 'name': str, 'seed': int, "
            "'steps': [{'step': n, 'action': str, 'name': str, 'params': {...}, 'group': str, 'blend': str, "
            "'opacity': float}, ..., {'action': 'preview', 'params': {'tag': 'stage'}}], "
            "'formats': ['png', 'jpeg'], 'notes': [str]}"))]) -> dict[str, Any]:
        """Build a whole image from a declarative pipeline: creates a new layered project, runs every step
        (tagged with its plan step), renders the requested previews, exports PNG/JPEG + layered ORA and
        writes pipeline.json. Returns paths of exports and previews - view them and iterate. For complex
        scenes prefer writing a Python pipeline (image_studio.pipeline.Pipeline) and running it."""
        return {"ok": True, **run_spec(spec, editor=ed)}

    @tool(title="Learn patterns from a reference")
    def learn_pattern(document_id: DocId, reference_id: str, name: str, rect: Rect | None = None,
                      fg_points: Points | None = None, bg_points: Points | None = None) -> dict[str, Any]:
        """Measure reusable patterns on a fetched reference: palette, dark-mark analysis (stripes/spots/
        plain, coverage, elongation), dominant period and direction, texture orientation, light direction and,
        when ``rect`` (around the subject) or fg_points is given, the subject's silhouette contour (GrabCut).
        Returns suggested pattern-library entries - review them (look at the reference!) and save_pattern the
        good ones so future tasks don't need to learn them again. Results are also written to research/."""
        proj = ed.project(document_id)
        rec, rgba = _reference(proj, reference_id)
        res = learn_from_image(rgba, rect=[int(v) for v in rect] if rect else None, fg_points=fg_points,
                               bg_points=bg_points, name=name)
        src = {"url": rec.get("source_page") or rec.get("image_url"), "title": rec.get("title"),
               "license": (rec.get("license") or {}).get("short_name")}
        for s in res["suggested"]:
            s["sources"] = [src]
        out = proj.path("research", f"patterns_{name}_{reference_id}.json")
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")
        if "silhouette" in res:
            res["silhouette"] = {**res["silhouette"], "points": f"{len(res['silhouette']['points'])} points "
                                 "(full list in the suggested silhouette entry)"}
        return {"ok": True, "reference_id": reference_id, "saved_to": str(out), **res}

    @tool(read_only=True, title="Search pattern library")
    def search_patterns(query: str, kind: str | None = None, limit: int = 10) -> dict[str, Any]:
        """Search learned/authored patterns (kinds: figure, texture, palette, silhouette, scene, light). Do this
        BEFORE researching: a hit means the subject or material was already studied."""
        return {"ok": True, "query": query, "results": lib.search(query, kind, limit),
                "total": len(lib.all())}

    @tool(read_only=True, title="Get pattern")
    def get_pattern(pattern_id: PatternId) -> dict[str, Any]:
        """Full pattern entry (params usable by paint actions, measurements, sources, notes)."""
        return {"ok": True, "pattern": lib.get(pattern_id).model_dump()}

    @tool(title="Save pattern")
    def save_pattern(pattern_id: PatternId, title: str, params: dict[str, Any], tags: list[str] | None = None,
                     sources: list[dict[str, Any]] | None = None, confidence: str = "medium", notes: str = "",
                     learned: dict[str, Any] | None = None, overwrite: bool = False) -> dict[str, Any]:
        """Save a reusable pattern (a figure recipe, measured texture, palette, silhouette, scene or light
        setup) to knowledge/patterns/. Cite sources (url, title, license); 'high' confidence needs sources.
        Tell the user to commit the file so it persists for everyone who clones the repository."""
        kind = pattern_id.split("/", 1)[0]
        entry = PatternEntry(id=pattern_id, kind=kind, title=title, params=params, tags=tags or [],
                             sources=sources or [], confidence=confidence, notes=notes, learned=learned or {})
        if lib.exists(pattern_id) and overwrite:
            old = lib.get(pattern_id)
            entry.used_in = old.used_in
        path = lib.save(entry, overwrite=overwrite)
        return {"ok": True, "path": str(path), "id": pattern_id,
                "hint": "Commit knowledge/patterns/ with git so the pattern persists."}

    @tool(mutating=True, title="Synthesize texture (clone-stamp quilting)")
    def synthesize_texture(document_id: DocId, reference_id: str, rect: Rect, width: int, height: int,
                           x: int = 0, y: int = 0, patch: int = 48, name: str | None = None, seed: int = 0,
                           license_acknowledged: bool = False) -> dict[str, Any]:
        """Grow a new, non-repeating texture (bark, fur, sand, water, foliage...) from a region ``rect`` of a
        reference by stamping and seam-cutting patches - the automated clone stamp. The output is a new layer
        of size width x height at (x, y). Because it reuses the reference's pixels, the license must allow
        derivatives (CC0/PD/CC BY/CC BY-SA); attribution is recorded."""
        proj = ed.project(document_id)
        rec, rgba = _reference(proj, reference_id)
        lic = LicenseInfo(**rec["license"]) if rec.get("license") else None
        verdict = assess_reuse(lic)
        if not verdict["composite_allowed"] and not license_acknowledged:
            raise ValidationError(f"Reference '{reference_id}' may not be reused as texture: {verdict['notes']}",
                                  hint="Use a CC0/PD/CC BY(-SA) reference, or only learn_pattern from it.")
        rx, ry, rw, rh = [int(v) for v in rect]
        ex = rgba[max(0, ry):ry + rh, max(0, rx):rx + rw]
        if ex.shape[0] < 16 or ex.shape[1] < 16:
            raise ValidationError("rect must cover at least 16x16 px of the reference")
        if not (16 <= width <= 8192 and 16 <= height <= 8192):
            raise ValidationError("width/height must be within 16..8192")
        tex = synthesis.quilt(canvas.from_u8(ex), width, height, patch=patch, seed=seed)
        arr = canvas.to_u8(canvas.layer(tex, 1.0))
        meta = {"synthesized_from": reference_id, "rect": [rx, ry, rw, rh], "license": verdict["code"],
                "attribution": attribution_line(lic, rec.get("title"))}
        res = ed.add_pixel_layer(document_id, arr, name or f"Texture from {reference_id}", x=x, y=y,
                                 metadata=meta, op="synthesize_texture", params={"reference_id": reference_id})
        if verdict["attribution_required"]:
            res.setdefault("warnings", []).append("Attribution required: " + (meta["attribution"] or "see license"))
        return res
