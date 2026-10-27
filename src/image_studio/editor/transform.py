"""Layer transforms with "smart" re-rendering from the original pixels."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..core import geometry
from ..core.layer import Layer, LayerKind
from ..errors import ValidationError
from .base import EditorBase
from .layers import _opaque_bbox

PIVOTS = {"center": (0.5, 0.5), "top_left": (0, 0), "top": (0.5, 0), "top_right": (1, 0), "left": (0, 0.5),
          "right": (1, 0.5), "bottom_left": (0, 1), "bottom": (0.5, 1), "bottom_right": (1, 1)}


class TransformOps(EditorBase):
    def _layer_doc_bbox(self, proj, layer: Layer) -> tuple[float, float, float, float]:
        """Opaque bounds in document coordinates (x0, y0, x1, y1)."""
        if layer.kind == LayerKind.group:
            boxes = [self._layer_doc_bbox(proj, proj.doc.layers[c]) for c in layer.children
                     if proj.doc.layers[c].pixels or proj.doc.layers[c].kind == LayerKind.group]
            boxes = [b for b in boxes if b[2] > b[0]]
            if not boxes:
                return (0, 0, 0, 0)
            return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                    max(b[3] for b in boxes))
        if not layer.pixels:
            return (0, 0, 0, 0)
        bbox = _opaque_bbox(proj.blobs.get(layer.pixels))
        if not bbox:
            return (layer.x, layer.y, layer.x, layer.y)
        return (layer.x + bbox[0], layer.y + bbox[1], layer.x + bbox[0] + bbox[2], layer.y + bbox[1] + bbox[3])

    def _apply_matrix(self, proj, tx, layer: Layer, T: np.ndarray | None, interpolation: str,
                      absolute: np.ndarray | None = None) -> None:
        if layer.kind == LayerKind.group:
            for cid in layer.children:
                self._apply_matrix(proj, tx, tx.doc.layers[cid], T, interpolation, absolute)
            return
        if layer.kind == LayerKind.adjustment or not layer.pixels:
            return
        self.check_editable(layer)
        if layer.base_blob and layer.transform:
            base = proj.blobs.get(layer.base_blob)
            m_old = np.array(layer.transform, np.float64)
        else:
            base = proj.blobs.get(layer.pixels)
            m_old = geometry.translation(layer.x, layer.y)
            layer.base_blob = layer.pixels
        m_new = absolute if absolute is not None else T @ m_old
        arr, nx, ny = geometry.warp(base, m_new, interpolation)
        if layer.mask:
            inc = m_new @ np.linalg.inv(m_old)
            mm = geometry.translation(-nx, -ny) @ inc @ geometry.translation(layer.x, layer.y)
            mask = proj.blobs.get(layer.mask.blob)
            h, w = arr.shape[:2]
            warped = cv2.warpPerspective(mask, mm, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                         borderValue=255)
            layer.mask.blob = proj.blobs.put(warped)
        layer.pixels = proj.blobs.put(arr)
        layer.transform = m_new.tolist()
        layer.x, layer.y = nx, ny
        layer.height, layer.width = arr.shape[:2]
        tx.touch(layer.id)

    def transform_layer(self, document_id: str, layer_id: str, *, translate_x: float = 0.0, translate_y: float = 0.0,
                        scale_x: float = 1.0, scale_y: float | None = None, rotate: float = 0.0,
                        shear_x: float = 0.0, shear_y: float = 0.0, flip_horizontal: bool = False,
                        flip_vertical: bool = False, pivot: str | list[float] = "center",
                        perspective: list[list[float]] | None = None,
                        interpolation: str = "cubic") -> dict[str, Any]:
        """Move/scale/rotate/shear/flip a layer about a pivot, or map it to 4 perspective corners.

        Rotation is in degrees, clockwise on screen. Repeated transforms are re-rendered from the
        original pixels, so quality doesn't degrade.
        """
        proj = self.project(document_id)
        sy = scale_x if scale_y is None else scale_y
        for v, nm in ((scale_x, "scale_x"), (sy, "scale_y")):
            if not 0.001 <= abs(v) <= 100:
                raise ValidationError(f"{nm} must be within 0.001..100 in magnitude")
        if not -89 < shear_x < 89 or not -89 < shear_y < 89:
            raise ValidationError("shear angles must be within -89..89 degrees")
        geometry.interp_flag(interpolation)
        params = dict(translate_x=translate_x, translate_y=translate_y, scale_x=scale_x, scale_y=sy, rotate=rotate,
                      shear_x=shear_x, shear_y=shear_y, flip_horizontal=flip_horizontal, flip_vertical=flip_vertical,
                      pivot=pivot, perspective=perspective)
        with proj.transaction("transform_layer", {"layer_id": layer_id, **params}) as tx:
            layer = tx.doc.layer(layer_id)
            if perspective is not None:
                if layer.kind == LayerKind.group:
                    raise ValidationError("Perspective transforms apply to single pixel layers, not groups")
                if not (isinstance(perspective, list) and len(perspective) == 4
                        and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in perspective)):
                    raise ValidationError("perspective must be 4 [x, y] corners: TL, TR, BR, BL (document coords)")
                if layer.base_blob and layer.transform:
                    bh, bw = proj.blobs.get(layer.base_blob).shape[:2]
                else:
                    bh, bw = layer.height, layer.width
                absolute = geometry.perspective_from_corners(bw, bh, perspective)
                self._apply_matrix(proj, tx, layer, None, interpolation, absolute)
            else:
                x0, y0, x1, y1 = self._layer_doc_bbox(proj, layer)
                if x1 <= x0 or y1 <= y0:
                    x0, y0, x1, y1 = layer.x, layer.y, layer.x + max(layer.width, 1), layer.y + max(layer.height, 1)
                if isinstance(pivot, str):
                    if pivot not in PIVOTS:
                        raise ValidationError(f"pivot must be one of {list(PIVOTS)} or [x, y] document coords")
                    fx, fy = PIVOTS[pivot]
                    px, py = x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy
                else:
                    px, py = float(pivot[0]), float(pivot[1])
                sxv = -scale_x if flip_horizontal else scale_x
                syv = -sy if flip_vertical else sy
                T = geometry.translation(translate_x, translate_y) @ geometry.scale_rotate_about(
                    px, py, sxv, syv, rotate, shear_x, shear_y)
                if np.allclose(T, np.eye(3)):
                    raise ValidationError("Transform is the identity; nothing to do")
                if np.allclose(T[:2, :2], np.eye(2)) and float(translate_x).is_integer() \
                        and float(translate_y).is_integer():
                    self._translate(tx, layer, int(translate_x), int(translate_y))
                    tx.touch(layer.id)
                else:
                    self._apply_matrix(proj, tx, layer, T, interpolation)
            tx.result["bounds"] = {"x": layer.x, "y": layer.y, "width": layer.width, "height": layer.height}
        return self.result(proj, tx)

    def rotate_layer(self, document_id: str, layer_id: str, angle: float, pivot: str | list[float] = "center",
                     interpolation: str = "cubic") -> dict[str, Any]:
        return self.transform_layer(document_id, layer_id, rotate=angle, pivot=pivot, interpolation=interpolation)

    def flip_layer(self, document_id: str, layer_id: str, direction: str = "horizontal") -> dict[str, Any]:
        if direction not in ("horizontal", "vertical"):
            raise ValidationError("direction must be horizontal or vertical")
        return self.transform_layer(document_id, layer_id, flip_horizontal=direction == "horizontal",
                                    flip_vertical=direction == "vertical", interpolation="nearest")

    def align_layers(self, document_id: str, layer_ids: list[str], alignment: str,
                     relative_to: str = "canvas") -> dict[str, Any]:
        """Align layers' visible content: left|center|right|top|middle|bottom, relative to canvas|selection|first."""
        proj = self.project(document_id)
        if alignment not in ("left", "center", "right", "top", "middle", "bottom"):
            raise ValidationError("alignment must be left, center, right, top, middle or bottom")
        if not layer_ids:
            raise ValidationError("layer_ids must not be empty")
        doc = proj.doc
        if relative_to == "canvas":
            ref = (0, 0, doc.width, doc.height)
        elif relative_to == "selection":
            sel = self.selection_doc(proj)
            ys, xs = np.nonzero(sel > 0.5)
            if len(xs) == 0:
                raise ValidationError("Selection is empty")
            ref = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        elif relative_to == "first":
            ref = self._layer_doc_bbox(proj, doc.layer(layer_ids[0]))
        else:
            raise ValidationError("relative_to must be canvas, selection or first")
        with proj.transaction("align_layers", {"layer_ids": layer_ids, "alignment": alignment,
                                               "relative_to": relative_to}) as tx:
            moves = {}
            for lid in layer_ids:
                layer = tx.doc.layer(lid)
                b = self._layer_doc_bbox(proj, layer)
                if b[2] <= b[0]:
                    continue
                dx = dy = 0.0
                if alignment == "left":
                    dx = ref[0] - b[0]
                elif alignment == "right":
                    dx = ref[2] - b[2]
                elif alignment == "center":
                    dx = (ref[0] + ref[2]) / 2 - (b[0] + b[2]) / 2
                elif alignment == "top":
                    dy = ref[1] - b[1]
                elif alignment == "bottom":
                    dy = ref[3] - b[3]
                else:
                    dy = (ref[1] + ref[3]) / 2 - (b[1] + b[3]) / 2
                self._translate(tx, layer, int(round(dx)), int(round(dy)))
                tx.touch(lid)
                moves[lid] = [int(round(dx)), int(round(dy))]
            tx.result["moves"] = moves
        return self.result(proj, tx)
