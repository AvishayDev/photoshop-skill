from __future__ import annotations

from typing import Any

from .common import DocId, LayerId, Point, Points, Strokes


def register(tool, session) -> None:
    ed = session.editor

    @tool(mutating=True, title="Create selection")
    def create_selection(document_id: DocId, shape: str = "rectangle", x: float = 0, y: float = 0,
                         width: float = 0, height: float = 0, points: Points | None = None, mode: str = "replace",
                         feather: float = 0.0) -> dict[str, Any]:
        """Create/combine the document selection. shape: all | none | rectangle | ellipse | polygon (points).
        mode: replace | add | subtract | intersect. feather in px. Selections drive masks, local adjustments,
        remove_object and fills."""
        return ed.create_selection(document_id, shape, x, y, width, height, points, mode, feather)

    @tool(mutating=True, title="Select by color")
    def select_by_color(document_id: DocId, layer_id: LayerId, color: str | None = None, point: Point | None = None,
                        tolerance: float = 32.0, contiguous: bool = False, mode: str = "replace",
                        feather: float = 0.0) -> dict[str, Any]:
        """Select pixels of a layer near a color (or the color under `point`). contiguous=true acts like a
        magic wand from `point`. tolerance is RGB distance 0..441 (32 is moderate)."""
        return ed.select_by_color(document_id, layer_id, color, point, tolerance, contiguous, mode, feather)

    @tool(mutating=True, title="Select layer pixels")
    def select_layer_alpha(document_id: DocId, layer_id: LayerId, mode: str = "replace") -> dict[str, Any]:
        """Select the visible pixels of a layer (alpha times mask)."""
        return ed.select_layer_alpha(document_id, layer_id, mode)

    @tool(mutating=True, title="Modify selection")
    def modify_selection(document_id: DocId, operation: str, amount: float = 0.0) -> dict[str, Any]:
        """invert | grow (px) | shrink (px) | feather (px) | border (px) | clear."""
        return ed.modify_selection(document_id, operation, amount)

    @tool(mutating=True, title="Create layer mask")
    def create_layer_mask(document_id: DocId, layer_id: LayerId, source: str = "white", start: Point | None = None,
                          end: Point | None = None, center: Point | None = None, radius: float | None = None,
                          source_layer_id: str | None = None, invert: bool = False,
                          replace: bool = False) -> dict[str, Any]:
        """Add a non-destructive mask (white = visible). source: white | black | selection | alpha | luminance |
        layer_luminance (of source_layer_id) | linear_gradient (white at start -> black at end) |
        radial_gradient (white center). Works on pixel layers, groups and adjustment layers."""
        return ed.create_layer_mask(document_id, layer_id, source, start, end, center, radius, source_layer_id,
                                    invert, replace)

    @tool(mutating=True, title="Edit layer mask")
    def edit_layer_mask(document_id: DocId, layer_id: LayerId, operation: str, value: float = 1.0,
                        strokes: Strokes | None = None, brush_size: float = 40.0, hardness: float = 0.5,
                        amount: float = 0.0, start: Point | None = None, end: Point | None = None,
                        center: Point | None = None, radius: float | None = None,
                        combine: str = "multiply") -> dict[str, Any]:
        """Edit a mask: paint (strokes; value 1 reveals, 0 hides; soft brush) | fill_selection | fill_all |
        gradient (linear start/end or radial center/radius; combine multiply|replace|max|min) | grow | shrink
        (amount px) | blur (amount px) | contrast (amount 0..1, hardens soft edges) | threshold (amount 0..1)."""
        return ed.edit_layer_mask(document_id, layer_id, operation, value, strokes, brush_size, hardness, amount,
                                  start, end, center, radius, combine)

    @tool(mutating=True, title="Invert mask")
    def invert_mask(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Invert a layer mask (hidden areas become visible and vice versa)."""
        return ed.invert_mask(document_id, layer_id)

    @tool(mutating=True, title="Feather mask")
    def feather_mask(document_id: DocId, layer_id: LayerId, radius: float) -> dict[str, Any]:
        """Soften mask edges by `radius` px (1-3 px for cut-outs; larger for blends)."""
        return ed.feather_mask(document_id, layer_id, radius)

    @tool(mutating=True, title="Enable/disable mask")
    def set_mask_enabled(document_id: DocId, layer_id: LayerId, enabled: bool) -> dict[str, Any]:
        """Temporarily disable a mask (to compare) or re-enable it."""
        return ed.set_mask_enabled(document_id, layer_id, enabled)

    @tool(mutating=True, destructive=True, title="Apply mask")
    def apply_mask(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Bake the mask into the layer's alpha (destructive; usually unnecessary)."""
        return ed.apply_mask(document_id, layer_id)

    @tool(mutating=True, title="Delete mask")
    def delete_mask(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Remove a layer mask without applying it."""
        return ed.delete_mask(document_id, layer_id)
