"""Pixel operations: filters, color adjustments, clone/heal, object & background removal."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..backends.base import CAP_CLONE, CAP_FILTER, CAP_HEAL
from ..core import adjustments as adj
from ..core import retouch
from ..core.color import f_to_u8, u8_to_f
from ..core.fx import lab_stats
from ..core.ids import new_id
from ..core.layer import AdjustmentProps, Layer, LayerKind, MaskRef
from ..core.selection import shape_mask
from ..errors import UnsupportedOperationError, ValidationError
from .base import EditorBase


class RetouchOps(EditorBase):
    # ----- helpers --------------------------------------------------------------------
    def _restrict(self, proj, doc, layer, before: np.ndarray, after: np.ndarray, use_selection: bool) -> np.ndarray:
        if not use_selection:
            return after
        s = self.doc_mask_to_layer(self.selection_doc(proj, doc), layer)[..., None]
        out = before.astype(np.float32) * (1 - s) + after.astype(np.float32) * s
        return np.clip(out + 0.5, 0, 255).astype(np.uint8)

    def _frame(self, proj, doc, frame: Layer, sample: str) -> np.ndarray:
        """Pixels to sample from, aligned to ``frame``'s local coordinates."""
        if sample == "layer":
            return self.pixels(proj, frame)
        if sample == "merged":
            canvas = f_to_u8(self.render_doc(proj, doc))
            src = np.zeros((frame.height, frame.width, 4), np.uint8)
            self._paste(src, canvas, -frame.x, -frame.y)
            return src
        other = doc.layer(sample)
        src = np.zeros((frame.height, frame.width, 4), np.uint8)
        self._paste(src, self.pixels(proj, other), other.x - frame.x, other.y - frame.y)
        return src

    @staticmethod
    def _paste(dst: np.ndarray, src: np.ndarray, ox: int, oy: int) -> None:
        H, W = dst.shape[:2]
        h, w = src.shape[:2]
        x0, y0, x1, y1 = max(0, ox), max(0, oy), min(W, ox + w), min(H, oy + h)
        if x1 > x0 and y1 > y0:
            dst[y0:y1, x0:x1] = src[y0 - oy:y1 - oy, x0 - ox:x1 - ox]

    @staticmethod
    def _local_strokes(strokes, layer) -> list[list[list[float]]]:
        if not isinstance(strokes, list) or not strokes:
            raise ValidationError("strokes must be a non-empty list of strokes, each a list of [x, y] points")
        out = []
        for s in strokes:
            if not isinstance(s, list) or not s:
                raise ValidationError("each stroke must be a non-empty list of [x, y] points")
            out.append([[float(p[0]) - layer.x, float(p[1]) - layer.y] for p in s])
        return out

    # ----- filters & adjustments -------------------------------------------------------
    def apply_filter(self, document_id: str, layer_id: str, filter: str, params: dict[str, Any] | None = None,
                     backend: str = "auto", use_selection: bool = False, target: str = "pixels") -> dict[str, Any]:
        """Apply a filter to a layer's pixels (or its mask with target='mask').
        Core filters work everywhere; 'gegl:*' operations require backend='gimp'."""
        proj = self.project(document_id)
        if filter.startswith("gegl:") and backend == "auto":
            backend = "gimp"
        b = self.backend_for(CAP_FILTER, backend)
        with proj.transaction("apply_filter", {"layer_id": layer_id, "filter": filter, "params": params or {},
                                               "use_selection": use_selection, "target": target},
                              backend=b.name) as tx:
            layer = tx.doc.layer(layer_id)
            if target == "mask":
                if not layer.mask:
                    raise ValidationError("Layer has no mask")
                m = proj.blobs.get(layer.mask.blob)
                rgba = np.dstack([m, m, m, np.full_like(m, 255)])
                out = b.apply_filter(rgba, filter, params or {})
                layer.mask.blob = proj.blobs.put(np.ascontiguousarray(out[..., 0]))
                tx.touch(layer_id)
            else:
                self.check_editable(layer)
                before = self.pixels(proj, layer)
                out = b.apply_filter(before, filter, params or {})
                self.set_pixels(proj, tx, layer, self._restrict(proj, tx.doc, layer, before, out, use_selection))
            tx.backend = b.name
        return self.result(proj, tx)

    def blur_layer(self, document_id: str, layer_id: str, radius: float = 4.0, method: str = "gaussian",
                   angle: float = 0.0, use_selection: bool = False) -> dict[str, Any]:
        """method: gaussian | box | motion (uses angle) | lens."""
        mapping = {"gaussian": ("gaussian_blur", {"radius": radius}), "box": ("box_blur", {"radius": int(radius)}),
                   "motion": ("motion_blur", {"distance": radius, "angle": angle}),
                   "lens": ("lens_blur", {"radius": radius})}
        if method not in mapping:
            raise ValidationError(f"method must be one of {list(mapping)}")
        name, params = mapping[method]
        return self.apply_filter(document_id, layer_id, name, params, backend="pillow", use_selection=use_selection)

    def sharpen_layer(self, document_id: str, layer_id: str, amount: float = 0.8, radius: float = 1.5,
                      threshold: float = 2.0, use_selection: bool = False) -> dict[str, Any]:
        return self.apply_filter(document_id, layer_id, "unsharp_mask",
                                 {"amount": amount, "radius": radius, "threshold": threshold},
                                 backend="pillow", use_selection=use_selection)

    def adjust_colors(self, document_id: str, layer_id: str | None, adjustment: str,
                      params: dict[str, Any] | None = None, use_selection: bool = False,
                      as_adjustment_layer: bool = False, clipped: bool = True,
                      name: str | None = None) -> dict[str, Any]:
        """Color/tone adjustment. Destructive on ``layer_id`` by default; with as_adjustment_layer=true a
        non-destructive adjustment layer is created above ``layer_id`` (clipped to it unless clipped=false),
        or at the top of the document when layer_id is omitted."""
        clean = adj.validate_params(adjustment, params)
        if as_adjustment_layer:
            return self.create_adjustment_layer(document_id, adjustment, clean, above=layer_id,
                                                clipped=bool(layer_id) and clipped, name=name,
                                                use_selection_as_mask=use_selection)
        if not layer_id:
            raise ValidationError("layer_id is required for destructive adjustments")
        proj = self.project(document_id)
        with proj.transaction("adjust_colors", {"layer_id": layer_id, "adjustment": adjustment, "params": clean,
                                                "use_selection": use_selection}) as tx:
            layer = tx.doc.layer(layer_id)
            self.check_editable(layer)
            before = self.pixels(proj, layer)
            f = u8_to_f(before)
            f[..., :3] = adj.apply_adjustment(f[..., :3], adjustment, clean)
            self.set_pixels(proj, tx, layer, self._restrict(proj, tx.doc, layer, before, f_to_u8(f), use_selection))
        return self.result(proj, tx)

    def adjust_curves(self, document_id: str, layer_id: str | None, points: list[list[float]] | None = None,
                      red: list[list[float]] | None = None, green: list[list[float]] | None = None,
                      blue: list[list[float]] | None = None, as_adjustment_layer: bool = True,
                      use_selection: bool = False) -> dict[str, Any]:
        params = {k: v for k, v in dict(points=points, red=red, green=green, blue=blue).items() if v}
        if not params:
            raise ValidationError("Provide at least one curve (points, red, green or blue)")
        return self.adjust_colors(document_id, layer_id, "curves", params, use_selection=use_selection,
                                  as_adjustment_layer=as_adjustment_layer)

    def create_adjustment_layer(self, document_id: str, adjustment: str, params: dict[str, Any] | None = None,
                                above: str | None = None, clipped: bool = False, name: str | None = None,
                                opacity: float = 1.0, use_selection_as_mask: bool = False) -> dict[str, Any]:
        proj = self.project(document_id)
        clean = adj.validate_params(adjustment, params)
        with proj.transaction("create_adjustment_layer", {"adjustment": adjustment, "params": clean, "above": above,
                                                          "clipped": clipped}) as tx:
            W, H = tx.doc.width, tx.doc.height
            layer = Layer(id=new_id("adj"), name=name or adjustment.replace("_", " ").title(),
                          kind=LayerKind.adjustment, width=W, height=H, opacity=opacity, clipped=clipped,
                          adjustment=AdjustmentProps(type=adjustment, params=clean))
            if use_selection_as_mask:
                s = self.selection_doc(proj, tx.doc)
                layer.mask = MaskRef(blob=proj.blobs.put(np.clip(s * 255 + 0.5, 0, 255).astype(np.uint8)))
            if above:
                ref = tx.doc.layer(above)
                anchor = self.clip_stack_top(tx.doc, above) if clipped else above
                tx.doc.insert(layer, parent_id=ref.parent_id, above=anchor)
            else:
                tx.doc.insert(layer)
            tx.touch(layer.id)
            tx.result["layer_id"] = layer.id
        return self.result(proj, tx)

    def update_adjustment_layer(self, document_id: str, layer_id: str, params: dict[str, Any]) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("update_adjustment_layer", {"layer_id": layer_id, "params": params}) as tx:
            layer = tx.doc.layer(layer_id)
            if layer.kind != LayerKind.adjustment or not layer.adjustment:
                raise ValidationError("Layer is not an adjustment layer")
            merged = {**layer.adjustment.params, **params}
            layer.adjustment.params = adj.validate_params(layer.adjustment.type, merged)
            tx.touch(layer_id)
        return self.result(proj, tx)

    def match_color(self, document_id: str, layer_id: str, reference: str = "below",
                    region: list[float] | None = None, strength: float = 0.7, preserve_luminance: bool = False,
                    as_adjustment_layer: bool = True) -> dict[str, Any]:
        """Match a layer's color statistics (CIE Lab mean/std) to a reference so a composited subject
        sits in the scene's light. reference = below (the composite under the layer, measured around it) |
        <layer_id> | region (with region=[x, y, w, h] of the current composite)."""
        proj = self.project(document_id)
        doc = proj.doc
        layer = doc.layer(layer_id)
        if not 0 <= strength <= 1:
            raise ValidationError("strength must be within 0..1")
        f = u8_to_f(self.pixels(proj, layer))
        weight = f[..., 3] * (u8_to_f(proj.blobs.get(layer.mask.blob)) if layer.mask else 1)
        src_mean, src_std = lab_stats(f[..., :3], weight)
        if reference == "below" or reference == "region":
            canvas = self.compositor(proj).render(stop_at=layer_id)
            if reference == "region":
                if not region or len(region) != 4:
                    raise ValidationError("region must be [x, y, width, height]")
                x, y, w, h = [int(v) for v in region]
                wmask = shape_mask(doc.width, doc.height, "rectangle", x=x, y=y, w=w, h=h)
            else:
                pad = int(max(layer.width, layer.height) * 0.6)
                wmask = shape_mask(doc.width, doc.height, "rectangle", x=layer.x - pad, y=layer.y - pad,
                                   w=layer.width + 2 * pad, h=layer.height + 2 * pad)
            wmask = wmask * canvas[..., 3]
            ref_mean, ref_std = lab_stats(canvas[..., :3], wmask)
        else:
            other = doc.layer(reference)
            o = u8_to_f(self.pixels(proj, other))
            ref_mean, ref_std = lab_stats(o[..., :3], o[..., 3])
        # keep the subject's own contrast character: transfer means fully, stds partially
        dst_std = [s + (r - s) * 0.5 for s, r in zip(src_std, ref_std)]
        params = {"src_mean": src_mean, "src_std": src_std, "dst_mean": ref_mean, "dst_std": dst_std,
                  "strength": strength, "preserve_luminance": preserve_luminance}
        res = self.adjust_colors(document_id, layer_id, "color_transfer", params,
                                 as_adjustment_layer=as_adjustment_layer, clipped=True,
                                 name=f"Color match: {layer.name}")
        res["measurements"] = {"subject_lab_mean": [round(v, 2) for v in src_mean],
                               "reference_lab_mean": [round(v, 2) for v in ref_mean]}
        return res

    # ----- retouching -----------------------------------------------------------------------
    def clone_stamp(self, document_id: str, layer_id: str, source_point: list[float],
                    strokes: list[list[list[float]]], brush_size: float = 30.0, hardness: float = 0.6,
                    opacity: float = 1.0, aligned: bool = True, sample: str = "layer", backend: str = "auto",
                    use_selection: bool = False) -> dict[str, Any]:
        """Clone stamp. Coordinates are document coordinates. ``source_point`` is where sampling starts;
        it corresponds to the first point of the first stroke. sample = layer | merged | <layer_id>."""
        proj = self.project(document_id)
        b = self.backend_for(CAP_CLONE, backend)
        with proj.transaction("clone_stamp", {"layer_id": layer_id, "source_point": source_point,
                                              "strokes": strokes, "brush_size": brush_size, "hardness": hardness,
                                              "opacity": opacity, "aligned": aligned, "sample": sample},
                              backend=b.name) as tx:
            layer = tx.doc.layer(layer_id)
            self.check_editable(layer)
            if not (isinstance(source_point, (list, tuple)) and len(source_point) == 2):
                raise ValidationError("source_point must be [x, y]")
            before = self.pixels(proj, layer)
            src = self._frame(proj, tx.doc, layer, sample)
            sp = (float(source_point[0]) - layer.x, float(source_point[1]) - layer.y)
            if not (0 <= sp[0] < layer.width and 0 <= sp[1] < layer.height):
                raise ValidationError("source_point lies outside the layer")
            local = self._local_strokes(strokes, layer)
            out, info = b.clone_stamp(before, src, source_point=sp, strokes=local, size=brush_size,
                                      hardness=hardness, opacity=opacity, aligned=aligned)
            self.set_pixels(proj, tx, layer, self._restrict(proj, tx.doc, layer, before, out, use_selection))
            tx.result["details"] = info
            tx.backend = b.name
        return self.result(proj, tx)

    def heal_region(self, document_id: str, layer_id: str, strokes: list[list[list[float]]],
                    source_point: list[float] | None = None, brush_size: float = 30.0, hardness: float = 0.5,
                    backend: str = "auto") -> dict[str, Any]:
        """Healing brush (with source_point: texture from the source, blended to local color and light) or
        spot healing (without source_point: reconstructs from surroundings). Document coordinates."""
        proj = self.project(document_id)
        b = self.backend_for(CAP_HEAL, backend)
        with proj.transaction("heal_region", {"layer_id": layer_id, "strokes": strokes,
                                              "source_point": source_point, "brush_size": brush_size},
                              backend=b.name) as tx:
            layer = tx.doc.layer(layer_id)
            self.check_editable(layer)
            before = self.pixels(proj, layer)
            sp = None if source_point is None else (source_point[0] - layer.x, source_point[1] - layer.y)
            out, info = b.heal(before, source_point=sp, strokes=self._local_strokes(strokes, layer),
                               size=brush_size, hardness=hardness)
            self.set_pixels(proj, tx, layer, out)
            tx.result["details"] = info
            tx.backend = b.name
        return self.result(proj, tx)

    def remove_object(self, document_id: str, layer_id: str, region: str = "selection",
                      rect: list[float] | None = None, polygon: list[list[float]] | None = None,
                      method: str = "telea", dilate: int = 4, radius: int = 6) -> dict[str, Any]:
        """Remove an object by reconstructing the region from its surroundings (OpenCV inpainting).
        region = selection | rect | polygon. Best for small/medium objects on textured backgrounds;
        check the preview and follow up with clone_stamp/heal_region for structure (edges, lines)."""
        proj = self.project(document_id)
        doc = proj.doc
        layer = doc.layer(layer_id)
        if region == "selection":
            m_doc = self.selection_doc(proj)
        elif region == "rect":
            if not rect or len(rect) != 4:
                raise ValidationError("rect must be [x, y, width, height]")
            m_doc = shape_mask(doc.width, doc.height, "rectangle", x=rect[0], y=rect[1], w=rect[2], h=rect[3])
        elif region == "polygon":
            m_doc = shape_mask(doc.width, doc.height, "polygon", points=polygon)
        else:
            raise ValidationError("region must be selection, rect or polygon")
        local = self.doc_mask_to_layer(m_doc, layer)
        frac = float((local > 0.5).mean())
        if frac == 0:
            raise ValidationError("The removal region does not overlap the layer")
        with proj.transaction("remove_object", {"layer_id": layer_id, "region": region, "rect": rect,
                                                "method": method, "dilate": dilate}) as tx:
            layer = tx.doc.layer(layer_id)
            self.check_editable(layer)
            out = retouch.inpaint(self.pixels(proj, layer), local, method=method, radius=radius, dilate=dilate)
            self.set_pixels(proj, tx, layer, out)
            tx.result["region_fraction"] = round(frac, 4)
            if frac > 0.08:
                tx.warnings.append("Large region: inpainting may smear. Inspect the preview; refine with "
                                   "clone_stamp/heal_region or a generative inpainting provider.")
        return self.result(proj, tx)

    def remove_background(self, document_id: str, layer_id: str, method: str = "grabcut",
                          rect: list[float] | None = None, foreground_points: list[list[float]] | None = None,
                          background_points: list[list[float]] | None = None, color: str | None = None,
                          tolerance: float = 40.0, iterations: int = 5, edge_feather: float = 1.0) -> dict[str, Any]:
        """Separate subject from background NON-destructively by creating a layer mask.
        method = grabcut (rect/seed points in document coords) | color_key (color + tolerance) |
        rembg (optional ML package). Original pixels stay intact."""
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        rgba = self.pixels(proj, layer)
        from ..core.selection import color_mask, feather
        if method == "grabcut":
            r = None
            if rect:
                r = (int(rect[0] - layer.x), int(rect[1] - layer.y), int(rect[2]), int(rect[3]))
            fg = [[p[0] - layer.x, p[1] - layer.y] for p in foreground_points or []]
            bg = [[p[0] - layer.x, p[1] - layer.y] for p in background_points or []]
            m = retouch.grabcut_mask(rgba, rect=r, fg_points=fg, bg_points=bg, iterations=iterations)
        elif method == "color_key":
            if not color:
                raise ValidationError("color_key needs color")
            m = 1 - color_mask(u8_to_f(rgba), color, tolerance)
        elif method == "rembg":
            try:
                from rembg import remove  # type: ignore
            except ImportError:
                raise UnsupportedOperationError("rembg is not installed",
                                                hint="pip install 'agent-image-studio[rembg]' (downloads a model "
                                                     "on first use)") from None
            from PIL import Image
            res = np.asarray(remove(Image.fromarray(rgba, "RGBA"))).copy()
            m = res[..., 3].astype(np.float32) / 255
        else:
            raise ValidationError("method must be grabcut, color_key or rembg")
        m = feather(m.astype(np.float32), edge_feather)
        with proj.transaction("remove_background", {"layer_id": layer_id, "method": method, "rect": rect}) as tx:
            layer = tx.doc.layer(layer_id)
            if layer.locked_pixels:
                tx.warnings.append("Layer pixels are locked; the mask was added without touching them")
            layer.mask = MaskRef(blob=proj.blobs.put(np.clip(m * 255 + 0.5, 0, 255).astype(np.uint8)))
            tx.touch(layer_id)
            tx.result.update(subject_fraction=round(float((m > 0.5).mean()), 4), method=method)
            tx.message = "Background hidden with a layer mask (refine with edit_layer_mask; apply_mask to bake)."
        return self.result(proj, tx)
