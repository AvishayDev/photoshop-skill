"""Document compositor.

Renders a :class:`Document` to a float RGBA canvas, honoring layer order,
groups (isolated and pass-through), masks, clipping masks, blend modes,
opacity, non-destructive adjustment layers and layer effects. Layers are
blended only inside their bounding box, so small layers on large canvases are
cheap.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..errors import ValidationError
from .adjustments import apply_adjustment
from .blending import composite
from .blobstore import BlobStore
from .color import parse_color, u8_to_f
from .document import Document
from .layer import BlendMode, Effect, Layer, LayerKind

EFFECT_DEFAULTS: dict[str, dict[str, Any]] = {
    "drop_shadow": {"color": "#000000", "opacity": 0.55, "direction_deg": 45.0, "distance": 12.0,
                    "size": 14.0, "spread": 0.0, "blend_mode": "multiply"},
    "outer_glow": {"color": "#fff3c4", "opacity": 0.6, "size": 18.0, "spread": 0.1, "blend_mode": "screen"},
    "stroke": {"color": "#000000", "opacity": 1.0, "width": 3.0, "blend_mode": "normal"},
}


def validate_effect(effect_type: str, params: dict[str, Any]) -> dict[str, Any]:
    if effect_type not in EFFECT_DEFAULTS:
        raise ValidationError(f"Unknown effect '{effect_type}'", details={"available": list(EFFECT_DEFAULTS)})
    unknown = set(params) - set(EFFECT_DEFAULTS[effect_type])
    if unknown:
        raise ValidationError(f"Unknown {effect_type} parameters: {sorted(unknown)}",
                              details={"accepted": EFFECT_DEFAULTS[effect_type]})
    merged = {**EFFECT_DEFAULTS[effect_type], **params}
    parse_color(merged["color"])
    BlendMode(merged["blend_mode"])
    if not 0 <= float(merged["opacity"]) <= 1:
        raise ValidationError("effect opacity must be within 0..1")
    for k in ("distance", "size", "width"):
        if k in merged and not 0 <= float(merged[k]) <= 1000:
            raise ValidationError(f"effect {k} must be within 0..1000")
    return merged


class _Stop(Exception):
    pass


class Compositor:
    def __init__(self, doc: Document, blobs: BlobStore):
        self.doc = doc
        self.blobs = blobs

    # ----- per-layer data ----------------------------------------------------
    def layer_rgba(self, layer: Layer) -> np.ndarray | None:
        if not layer.pixels:
            return None
        return u8_to_f(self.blobs.get(layer.pixels))

    def layer_mask(self, layer: Layer) -> np.ndarray | None:
        if layer.mask is None or not layer.mask.enabled:
            return None
        return u8_to_f(self.blobs.get(layer.mask.blob))

    def selection(self) -> np.ndarray | None:
        if not self.doc.selection:
            return None
        return u8_to_f(self.blobs.get(self.doc.selection))

    # ----- rendering ---------------------------------------------------------
    def render(self, *, stop_at: str | None = None, hidden: set[str] | None = None,
               solo: str | None = None, background: str | None = None) -> np.ndarray:
        """Render the document.

        stop_at: render only what lies *below* this layer (useful for sampling the backdrop).
        hidden: extra layer ids to treat as invisible.
        solo: render only this layer (and its children) on transparency.
        """
        H, W = self.doc.height, self.doc.width
        canvas = np.zeros((H, W, 4), np.float32)
        if background:
            c = np.array(parse_color(background), np.float32) / 255
            canvas[...] = c
        self._hidden = hidden or set()
        self._stop_at = stop_at
        if solo:
            layer = self.doc.layer(solo)
            ids = [solo]
            saved_visible = layer.visible
            layer.visible = True
            try:
                self._render_stack(ids, canvas)
            finally:
                layer.visible = saved_visible
            return canvas
        try:
            self._render_stack(self.doc.root, canvas)
        except _Stop:
            pass
        return canvas

    def _region(self, x: int, y: int, w: int, h: int):
        H, W = self.doc.height, self.doc.width
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            return None
        return (slice(y0, y1), slice(x0, x1)), (slice(y0 - y, y1 - y), slice(x0 - x, x1 - x))

    def _render_stack(self, ids: list[str], canvas: np.ndarray) -> None:
        clip_alpha: np.ndarray | None = None  # doc-space alpha of the current clipping base
        for lid in ids:
            layer = self.doc.layers[lid]
            if lid == self._stop_at:
                raise _Stop
            if not layer.clipped:
                clip_alpha = None
            visible = layer.visible and lid not in self._hidden
            if not visible:
                if not layer.clipped:
                    clip_alpha = np.zeros(canvas.shape[:2], np.float32)
                continue
            if layer.kind == LayerKind.group:
                self._render_group(layer, canvas, clip_alpha if layer.clipped else None)
                if not layer.clipped:
                    clip_alpha = None
                continue
            if layer.kind == LayerKind.adjustment:
                self._render_adjustment(layer, canvas, clip_alpha if layer.clipped else None)
                continue
            base_alpha = self._render_layer(layer, canvas, clip_alpha if layer.clipped else None)
            if not layer.clipped:
                clip_alpha = base_alpha

    def _render_layer(self, layer: Layer, canvas: np.ndarray, clip: np.ndarray | None) -> np.ndarray:
        H, W = canvas.shape[:2]
        rgba = self.layer_rgba(layer)
        doc_alpha = np.zeros((H, W), np.float32)
        if rgba is None:
            return doc_alpha
        mask = self.layer_mask(layer)
        if mask is not None:
            rgba = rgba.copy()
            rgba[..., 3] *= mask
        for eff in layer.effects:
            if eff.enabled and eff.type in ("drop_shadow", "outer_glow"):
                self._render_effect(layer, eff, rgba, canvas, clip)
        reg = self._region(layer.x, layer.y, layer.width, layer.height)
        if reg is None:
            return doc_alpha
        (dy, dx), (sy, sx) = reg
        src = rgba[sy, sx]
        m = None if clip is None else clip[dy, dx]
        canvas[dy, dx] = composite(canvas[dy, dx], src, layer.blend_mode, layer.opacity, m)
        doc_alpha[dy, dx] = src[..., 3] * layer.opacity * (1 if m is None else m)
        for eff in layer.effects:
            if eff.enabled and eff.type == "stroke":
                self._render_effect(layer, eff, rgba, canvas, clip)
        return doc_alpha

    def _render_effect(self, layer: Layer, eff: Effect, rgba: np.ndarray, canvas: np.ndarray,
                       clip: np.ndarray | None) -> None:
        p = validate_effect(eff.type, eff.params)
        alpha = rgba[..., 3]
        size = float(p.get("size", p.get("width", 0)))
        pad = int(np.ceil(size * 2 + float(p.get("distance", 0)) + 4))
        a = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
        ox, oy = layer.x - pad, layer.y - pad
        if eff.type == "drop_shadow":
            rad = np.deg2rad(float(p["direction_deg"]))
            ox += int(round(np.cos(rad) * float(p["distance"])))
            oy += int(round(np.sin(rad) * float(p["distance"])))
        if eff.type in ("drop_shadow", "outer_glow"):
            spread = float(p.get("spread", 0))
            if spread > 0 and size > 0:
                k = max(1, int(size * spread))
                a = cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
            if size > 0:
                a = cv2.GaussianBlur(a, (0, 0), max(size / 2, 0.5))
        elif eff.type == "stroke":
            k = max(1, int(round(float(p["width"]))))
            dil = cv2.dilate(a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
            a = np.clip(dil - a, 0, 1)
        color = np.array(parse_color(p["color"]), np.float32) / 255
        layer_buf = np.empty(a.shape + (4,), np.float32)
        layer_buf[..., :3] = color[:3]
        layer_buf[..., 3] = a * color[3]
        reg = self._region(ox, oy, a.shape[1], a.shape[0])
        if reg is None:
            return
        (dy, dx), (sy, sx) = reg
        m = None if clip is None else clip[dy, dx]
        canvas[dy, dx] = composite(canvas[dy, dx], layer_buf[sy, sx], BlendMode(p["blend_mode"]),
                                   float(p["opacity"]) * layer.opacity, m)

    def _render_group(self, layer: Layer, canvas: np.ndarray, clip: np.ndarray | None) -> None:
        H, W = canvas.shape[:2]
        mask_doc = self._doc_space_mask(layer, H, W)
        if clip is not None:
            mask_doc = clip if mask_doc is None else mask_doc * clip
        if layer.blend_mode == BlendMode.pass_through:
            before = canvas.copy()
            try:
                self._render_stack(layer.children, canvas)
            finally:
                t = layer.opacity if mask_doc is None else layer.opacity * mask_doc[..., None]
                if not (mask_doc is None and layer.opacity >= 1):
                    canvas[...] = before + (canvas - before) * t
            return
        buf = np.zeros_like(canvas)
        stopped = False
        try:
            self._render_stack(layer.children, buf)
        except _Stop:
            stopped = True
        canvas[...] = composite(canvas, buf, layer.blend_mode, layer.opacity, mask_doc)
        if stopped:
            raise _Stop

    def _render_adjustment(self, layer: Layer, canvas: np.ndarray, clip: np.ndarray | None) -> None:
        if not layer.adjustment:
            return
        H, W = canvas.shape[:2]
        adjusted = apply_adjustment(canvas[..., :3], layer.adjustment.type, layer.adjustment.params)
        t = np.full((H, W), layer.opacity, np.float32)
        m = self._doc_space_mask(layer, H, W)
        if m is not None:
            t *= m
        if clip is not None:
            t *= clip
        canvas[..., :3] = canvas[..., :3] + (adjusted - canvas[..., :3]) * t[..., None]

    def _doc_space_mask(self, layer: Layer, H: int, W: int) -> np.ndarray | None:
        mask = self.layer_mask(layer)
        if mask is None:
            return None
        out = np.zeros((H, W), np.float32)
        reg = self._region(layer.x, layer.y, mask.shape[1], mask.shape[0])
        if reg is not None:
            (dy, dx), (sy, sx) = reg
            out[dy, dx] = mask[sy, sx]
        return out


def flatten_to_u8(canvas: np.ndarray, background: str | None = None) -> np.ndarray:
    """Convert a float RGBA canvas to uint8, optionally over an opaque background color."""
    if background:
        bg = np.zeros_like(canvas)
        bg[...] = np.array(parse_color(background), np.float32) / 255
        canvas = composite(bg, canvas)
    return np.clip(canvas * 255 + 0.5, 0, 255).astype(np.uint8)
