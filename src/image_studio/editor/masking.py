"""Selections and layer masks."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core import selection as sel
from ..core.color import luminance, u8_to_f
from ..core.layer import LayerKind, MaskRef
from ..errors import ValidationError
from .base import EditorBase


def _to_u8(m: np.ndarray) -> np.ndarray:
    return np.clip(m * 255 + 0.5, 0, 255).astype(np.uint8)


class MaskOps(EditorBase):
    # ----- selections -------------------------------------------------------------------
    def _store_selection(self, proj, tx, mask: np.ndarray | None) -> dict[str, Any]:
        if mask is None or not (mask > 0.004).any():
            tx.doc.selection = None
            return {"selection": None}
        tx.doc.selection = proj.blobs.put(_to_u8(mask))
        ys, xs = np.nonzero(mask > 0.5)
        info = {"selected_fraction": round(float((mask > 0.5).mean()), 5)}
        if len(xs):
            info["bounds"] = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
        return {"selection": info}

    def create_selection(self, document_id: str, shape: str = "rectangle", x: float = 0, y: float = 0,
                         width: float = 0, height: float = 0, points: list[list[float]] | None = None,
                         mode: str = "replace", feather: float = 0.0, antialias: bool = True) -> dict[str, Any]:
        """Create or combine a selection: shape = all | none | rectangle | ellipse | polygon (document coords)."""
        proj = self.project(document_id)
        with proj.transaction("create_selection", {"shape": shape, "x": x, "y": y, "width": width, "height": height,
                                                   "points": points, "mode": mode, "feather": feather}) as tx:
            W, H = tx.doc.width, tx.doc.height
            new = sel.shape_mask(W, H, shape, x=x, y=y, w=width, h=height, points=points, antialias=antialias)
            new = sel.feather(new, feather)
            existing = self.selection_doc(proj, tx.doc, required=False)
            combined = sel.combine(existing, new, mode) if shape != "none" else None
            tx.result.update(self._store_selection(proj, tx, combined))
        return self.result(proj, tx)

    def select_by_color(self, document_id: str, layer_id: str, color: str | None = None,
                        point: list[float] | None = None, tolerance: float = 32.0, contiguous: bool = False,
                        mode: str = "replace", feather: float = 0.0) -> dict[str, Any]:
        """Select pixels of a layer similar to a color (or to the color under ``point``, document coords).
        contiguous=true behaves like a magic wand from ``point``."""
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        rgba = u8_to_f(self.pixels(proj, layer))
        seed = None
        if point is not None:
            lx, ly = int(point[0] - layer.x), int(point[1] - layer.y)
            if not (0 <= lx < layer.width and 0 <= ly < layer.height):
                raise ValidationError("point lies outside the layer")
            seed = (lx, ly)
            if color is None:
                color = [int(c * 255) for c in rgba[ly, lx, :3]]
        if color is None:
            raise ValidationError("Provide color or point")
        if contiguous and seed is None:
            raise ValidationError("contiguous selection needs a seed point")
        local = sel.color_mask(rgba, color, tolerance, contiguous_from=seed if contiguous else None)
        with proj.transaction("select_by_color", {"layer_id": layer_id, "color": color, "point": point,
                                                  "tolerance": tolerance, "contiguous": contiguous,
                                                  "mode": mode}) as tx:
            doc_mask = np.zeros((tx.doc.height, tx.doc.width), np.float32)
            self._paste_local(doc_mask, local, layer)
            doc_mask = sel.feather(doc_mask, feather)
            combined = sel.combine(self.selection_doc(proj, tx.doc, required=False), doc_mask, mode)
            tx.result.update(self._store_selection(proj, tx, combined))
        return self.result(proj, tx)

    def select_layer_alpha(self, document_id: str, layer_id: str, mode: str = "replace",
                           threshold: float = 0.0) -> dict[str, Any]:
        """Select a layer's visible pixels (its alpha, times its mask)."""
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        rgba = u8_to_f(self.pixels(proj, layer))
        a = rgba[..., 3]
        if layer.mask and layer.mask.enabled:
            a = a * u8_to_f(proj.blobs.get(layer.mask.blob))
        if threshold > 0:
            a = (a >= threshold).astype(np.float32)
        with proj.transaction("select_layer_alpha", {"layer_id": layer_id, "mode": mode}) as tx:
            doc_mask = np.zeros((tx.doc.height, tx.doc.width), np.float32)
            self._paste_local(doc_mask, a, layer)
            combined = sel.combine(self.selection_doc(proj, tx.doc, required=False), doc_mask, mode)
            tx.result.update(self._store_selection(proj, tx, combined))
        return self.result(proj, tx)

    def modify_selection(self, document_id: str, operation: str, amount: float = 0.0) -> dict[str, Any]:
        """invert | grow | shrink | feather | clear | border."""
        proj = self.project(document_id)
        with proj.transaction("modify_selection", {"operation": operation, "amount": amount}) as tx:
            if operation == "clear":
                tx.result.update(self._store_selection(proj, tx, None))
            else:
                cur = self.selection_doc(proj, tx.doc, required=operation != "invert")
                if cur is None:
                    cur = np.zeros((tx.doc.height, tx.doc.width), np.float32)
                if operation == "invert":
                    new = 1 - cur
                elif operation == "grow":
                    new = sel.grow(cur, int(amount))
                elif operation == "shrink":
                    new = sel.grow(cur, -int(amount))
                elif operation == "feather":
                    new = sel.feather(cur, amount)
                elif operation == "border":
                    new = np.clip(sel.grow(cur, int(amount)) - sel.grow(cur, -int(amount)), 0, 1)
                else:
                    raise ValidationError("operation must be invert, grow, shrink, feather, border or clear")
                tx.result.update(self._store_selection(proj, tx, new))
        return self.result(proj, tx)

    def _paste_local(self, doc_mask: np.ndarray, local: np.ndarray, layer) -> None:
        H, W = doc_mask.shape
        x0, y0 = max(0, layer.x), max(0, layer.y)
        x1, y1 = min(W, layer.x + local.shape[1]), min(H, layer.y + local.shape[0])
        if x1 > x0 and y1 > y0:
            doc_mask[y0:y1, x0:x1] = local[y0 - layer.y:y1 - layer.y, x0 - layer.x:x1 - layer.x]

    # ----- layer masks -------------------------------------------------------------------
    def _mask_dims(self, layer) -> tuple[int, int]:
        if layer.width < 1 or layer.height < 1:
            raise ValidationError("Layer has no extent for a mask")
        return layer.height, layer.width

    def create_layer_mask(self, document_id: str, layer_id: str, source: str = "white",
                          start: list[float] | None = None, end: list[float] | None = None,
                          center: list[float] | None = None, radius: float | None = None,
                          source_layer_id: str | None = None, invert: bool = False,
                          replace: bool = False) -> dict[str, Any]:
        """Add a mask. source = white | black | selection | alpha | luminance | linear_gradient |
        radial_gradient | layer_luminance (luminance of ``source_layer_id``). Gradient coords are document coords."""
        proj = self.project(document_id)
        with proj.transaction("create_layer_mask", {"layer_id": layer_id, "source": source, "start": start,
                                                    "end": end, "center": center, "radius": radius,
                                                    "invert": invert}) as tx:
            layer = tx.doc.layer(layer_id)
            if layer.mask and not replace:
                raise ValidationError("Layer already has a mask", hint="Use edit_layer_mask, or replace=true")
            if layer.kind in (LayerKind.group, LayerKind.adjustment):
                layer.x = layer.y = 0
                layer.width, layer.height = tx.doc.width, tx.doc.height
            h, w = self._mask_dims(layer)
            m = self._mask_source(proj, tx.doc, layer, source, start, end, center, radius, source_layer_id)
            if invert:
                m = 1 - m
            layer.mask = MaskRef(blob=proj.blobs.put(_to_u8(m)))
            tx.touch(layer_id)
            tx.result["mask_coverage"] = round(float(m.mean()), 4)
        return self.result(proj, tx)

    def _mask_source(self, proj, doc, layer, source, start, end, center, radius, source_layer_id) -> np.ndarray:
        h, w = layer.height, layer.width
        if source == "white":
            return np.ones((h, w), np.float32)
        if source == "black":
            return np.zeros((h, w), np.float32)
        if source == "selection":
            return self.doc_mask_to_layer(self.selection_doc(proj, doc), layer)
        if source == "alpha":
            return u8_to_f(self.pixels(proj, layer))[..., 3]
        if source == "luminance":
            return luminance(u8_to_f(self.pixels(proj, layer))[..., :3])
        if source == "layer_luminance":
            other = doc.layer(source_layer_id or "")
            o = u8_to_f(self.pixels(proj, other))
            full = np.zeros((doc.height, doc.width), np.float32)
            self._paste_local(full, luminance(o[..., :3]) * o[..., 3], other)
            return self.doc_mask_to_layer(full, layer)
        if source == "linear_gradient":
            if not start or not end:
                raise ValidationError("linear_gradient needs start and end [x, y] (document coords); "
                                      "the mask is white at start and black at end")
            return sel.linear_gradient_mask(w, h, (start[0] - layer.x, start[1] - layer.y),
                                            (end[0] - layer.x, end[1] - layer.y))
        if source == "radial_gradient":
            if not center or not radius:
                raise ValidationError("radial_gradient needs center [x, y] and radius (white center)")
            return sel.radial_gradient_mask(w, h, (center[0] - layer.x, center[1] - layer.y), float(radius))
        raise ValidationError("Unknown mask source", details={"available": [
            "white", "black", "selection", "alpha", "luminance", "layer_luminance", "linear_gradient",
            "radial_gradient"]})

    def edit_layer_mask(self, document_id: str, layer_id: str, operation: str, value: float = 1.0,
                        strokes: list[list[list[float]]] | None = None, brush_size: float = 40.0,
                        hardness: float = 0.5, amount: float = 0.0, start: list[float] | None = None,
                        end: list[float] | None = None, center: list[float] | None = None,
                        radius: float | None = None, combine: str = "multiply") -> dict[str, Any]:
        """Edit a mask. operation =
        paint (strokes in document coords; value 1 reveals, 0 hides) | fill_selection | fill_all |
        gradient (linear start/end or radial center/radius, combined via 'multiply'|'replace'|'max'|'min') |
        grow | shrink | blur | contrast (amount 0..1 hardens edges) | threshold (amount 0..1)."""
        proj = self.project(document_id)
        with proj.transaction("edit_layer_mask", {"layer_id": layer_id, "operation": operation, "value": value,
                                                  "strokes": strokes, "brush_size": brush_size, "amount": amount}) as tx:
            layer = tx.doc.layer(layer_id)
            if not layer.mask:
                raise ValidationError("Layer has no mask", hint="Call create_layer_mask first")
            m = u8_to_f(proj.blobs.get(layer.mask.blob))
            if not 0 <= value <= 1:
                raise ValidationError("value must be within 0..1")
            if operation == "paint":
                if not strokes:
                    raise ValidationError("paint needs strokes: [[[x, y], ...], ...] in document coordinates")
                local = [[[p[0] - layer.x, p[1] - layer.y] for p in s] for s in strokes]
                brush = sel.brush_strokes_mask(m.shape[1], m.shape[0], local, brush_size, hardness)
                m = m * (1 - brush) + value * brush
            elif operation == "fill_selection":
                s = self.doc_mask_to_layer(self.selection_doc(proj, tx.doc), layer)
                m = m * (1 - s) + value * s
            elif operation == "fill_all":
                m[:] = value
            elif operation == "gradient":
                g = self._mask_source(proj, tx.doc, layer, "linear_gradient" if start else "radial_gradient",
                                      start, end, center, radius, None)
                m = {"multiply": m * g, "replace": g, "max": np.maximum(m, g), "min": np.minimum(m, g)}.get(combine)
                if m is None:
                    raise ValidationError("combine must be multiply, replace, max or min")
            elif operation in ("grow", "shrink"):
                m = sel.grow(m, int(amount) * (1 if operation == "grow" else -1))
            elif operation == "blur":
                m = sel.feather(m, amount)
            elif operation == "contrast":
                k = 1 + 20 * max(0.0, min(1.0, amount))
                m = np.clip((m - 0.5) * k + 0.5, 0, 1)
            elif operation == "threshold":
                m = (m >= (amount or 0.5)).astype(np.float32)
            else:
                raise ValidationError("Unknown mask operation", details={"available": [
                    "paint", "fill_selection", "fill_all", "gradient", "grow", "shrink", "blur", "contrast",
                    "threshold"]})
            layer.mask.blob = proj.blobs.put(_to_u8(m))
            tx.touch(layer_id)
            tx.result["mask_coverage"] = round(float(m.mean()), 4)
        return self.result(proj, tx)

    def invert_mask(self, document_id: str, layer_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("invert_mask", {"layer_id": layer_id}) as tx:
            layer = tx.doc.layer(layer_id)
            if not layer.mask:
                raise ValidationError("Layer has no mask")
            layer.mask.blob = proj.blobs.put(255 - proj.blobs.get(layer.mask.blob))
            tx.touch(layer_id)
        return self.result(proj, tx)

    def feather_mask(self, document_id: str, layer_id: str, radius: float) -> dict[str, Any]:
        if radius <= 0 or radius > 500:
            raise ValidationError("radius must be within (0, 500]")
        return self.edit_layer_mask(document_id, layer_id, "blur", amount=radius)

    def set_mask_enabled(self, document_id: str, layer_id: str, enabled: bool) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("set_mask_enabled", {"layer_id": layer_id, "enabled": enabled}) as tx:
            layer = tx.doc.layer(layer_id)
            if not layer.mask:
                raise ValidationError("Layer has no mask")
            layer.mask.enabled = enabled
            tx.touch(layer_id)
        return self.result(proj, tx)

    def apply_mask(self, document_id: str, layer_id: str) -> dict[str, Any]:
        """Bake the mask into the layer's alpha (destructive; undo available)."""
        proj = self.project(document_id)
        with proj.transaction("apply_mask", {"layer_id": layer_id}) as tx:
            layer = tx.doc.layer(layer_id)
            if not layer.mask:
                raise ValidationError("Layer has no mask")
            self.check_editable(layer)
            arr = self.pixels(proj, layer).copy()
            m = u8_to_f(proj.blobs.get(layer.mask.blob))
            arr[..., 3] = np.clip(arr[..., 3] * m + 0.5, 0, 255).astype(np.uint8)
            layer.mask = None
            self.set_pixels(proj, tx, layer, arr)
        return self.result(proj, tx)

    def delete_mask(self, document_id: str, layer_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("delete_mask", {"layer_id": layer_id}) as tx:
            layer = tx.doc.layer(layer_id)
            if not layer.mask:
                raise ValidationError("Layer has no mask")
            layer.mask = None
            tx.touch(layer_id)
        return self.result(proj, tx)
