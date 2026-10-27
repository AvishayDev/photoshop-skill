from __future__ import annotations

from typing import Any

import numpy as np

from ...core.color import f_to_u8, u8_to_f
from ...core.compositor import Compositor
from ...editor.base import load_rgba
from ...errors import ValidationError
from ...security import resolve_read_path
from ...workflows import quality_check as qc
from .common import DocId, LayerId, Rect


def register(tool, session) -> None:
    ed = session.editor

    def _doc_array(document_id: str, revision: int | None = None, region=None) -> np.ndarray:
        proj = ed.project(document_id)
        if revision is None or revision == proj.doc.revision:
            canvas = ed.render_doc(proj)
        else:
            canvas = Compositor(proj.load_revision(revision), proj.blobs).render()
        arr = f_to_u8(canvas)
        if region:
            x, y, w, h = [int(v) for v in region]
            arr = arr[y:y + h, x:x + w]
            if arr.size == 0:
                raise ValidationError("region is outside the canvas")
        return arr

    @tool(read_only=True, title="Inspect image")
    def inspect_image(document_id: str | None = None, path: str | None = None, region: Rect | None = None
                      ) -> dict[str, Any]:
        """Objective measurements of the current composite (or an image file): tonal range, clipping,
        contrast, saturation, color cast, sharpness, noise, dominant palette, global light gradient, and
        heuristic defect flags (clipping, flatness, casts, repeated clone patches). Complements - never
        replaces - looking at the preview yourself."""
        if bool(document_id) == bool(path):
            raise ValidationError("Provide exactly one of document_id or path")
        arr = _doc_array(document_id, region=region) if document_id else load_rgba(resolve_read_path(path))[0]
        return {"ok": True, **qc.inspect_array(arr)}

    @tool(read_only=True, title="Compare images")
    def compare_images(path_a: str | None = None, path_b: str | None = None, document_id: str | None = None,
                       revision_a: int | None = None, revision_b: int | None = None) -> dict[str, Any]:
        """Compare two images: two files, or two revisions of a document (revision_b defaults to current).
        Returns SSIM, mean difference, changed fraction/bounds and a difference heatmap path."""
        if document_id:
            if revision_a is None:
                raise ValidationError("revision_a is required when comparing document revisions")
            a = _doc_array(document_id, revision_a)
            b = _doc_array(document_id, revision_b)
            out_dir = ed.project(document_id).root / "previews"
        else:
            if not (path_a and path_b):
                raise ValidationError("Provide path_a and path_b, or document_id and revision_a")
            a = load_rgba(resolve_read_path(path_a))[0]
            b = load_rgba(resolve_read_path(path_b))[0]
            out_dir = ed.workspace / ".compare"
            out_dir.mkdir(exist_ok=True)
        res = qc.compare_arrays(a, b)
        diff = res.pop("_diff_map")
        heat = out_dir / f"diff_{revision_a or 'a'}_{revision_b or 'b'}.png"
        qc.save_heatmap(diff, heat)
        return {"ok": True, **res, "heatmap_path": str(heat)}

    @tool(read_only=True, title="Analyze layer integration")
    def analyze_layer_integration(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Check how well a composited subject layer fits its surroundings: brightness, color temperature,
        contrast, sharpness and grain vs. the backdrop around it, plus hard edges and halos. Returns concrete
        findings with suggested fixes."""
        proj = ed.project(document_id)
        doc = proj.doc
        layer = doc.layer(layer_id)
        comp = ed.compositor(proj)
        below = comp.render(stop_at=layer_id)
        full = ed.render_doc(proj)
        alpha = np.zeros((doc.height, doc.width), np.float32)
        rgba = u8_to_f(ed.pixels(proj, layer))
        a = rgba[..., 3] * (u8_to_f(proj.blobs.get(layer.mask.blob)) if layer.mask and layer.mask.enabled else 1)
        ed._paste_local(alpha, a, layer)
        if (alpha > 0.5).sum() < 50:
            raise ValidationError("The layer has too few visible pixels on the canvas to analyze")
        return {"ok": True, "layer": layer.name, **qc.integration_report(below, rgba, alpha, full)}
