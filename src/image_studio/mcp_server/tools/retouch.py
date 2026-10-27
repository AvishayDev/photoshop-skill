from __future__ import annotations

from typing import Any

from ...core.adjustments import SPECS
from ...core.filters import FILTERS
from .common import DocId, LayerId, Params, Point, Points, Rect, Strokes

_ADJ = ", ".join(f"{k}({', '.join(v.params)})" for k, v in SPECS.items())
_FIL = ", ".join(f"{k}({', '.join(v[1])})" for k, v in FILTERS.items())


def register(tool, session) -> None:
    ed = session.editor

    def apply_filter(document_id: DocId, layer_id: LayerId, filter: str, params: Params = None,
                     backend: str = "auto", use_selection: bool = False, target: str = "pixels") -> dict[str, Any]:
        return ed.apply_filter(document_id, layer_id, filter, params, backend, use_selection, target)
    apply_filter.__doc__ = (
        "Apply a filter to a layer (target='pixels') or to its mask (target='mask'), optionally only inside the "
        f"selection. Built-in filters: {_FIL}. With backend='gimp' any available GEGL operation can be used, "
        "e.g. filter='gegl:noise-reduction' params={'iterations': 3} (GEGL property names; see "
        "get_capabilities(include_gimp_filters=true) and describe_gimp_filter).")
    tool(mutating=True, title="Apply filter")(apply_filter)

    @tool(read_only=True, title="Describe GIMP filter")
    def describe_gimp_filter(operation: str) -> dict[str, Any]:
        """List the properties (name, type, range, default) of a GEGL operation in the installed GIMP 3."""
        from ...core.capabilities import backends
        return {"ok": True, **backends()["gimp"].filter_info(operation)}

    def adjust_colors(document_id: DocId, layer_id: str | None, adjustment: str, params: Params = None,
                      use_selection: bool = False, as_adjustment_layer: bool = False, clipped: bool = True,
                      name: str | None = None) -> dict[str, Any]:
        return ed.adjust_colors(document_id, layer_id, adjustment, params, use_selection, as_adjustment_layer,
                                clipped, name)
    adjust_colors.__doc__ = (
        "Color/tone adjustment. Prefer as_adjustment_layer=true (non-destructive, editable later, clipped to "
        "layer_id unless clipped=false; omit layer_id for a global grade on top). Otherwise edits layer_id's "
        f"pixels. Adjustments and parameters: {_ADJ}. Ranges: brightness/contrast/saturation/lightness/vibrance/"
        "temperature/tint -1..1, hue -180..180 deg, exposure ev -10..10, levels/curves values 0..255, "
        "color_balance triplets [cyan-red, magenta-green, yellow-blue] in -1..1.")
    tool(mutating=True, title="Adjust colors")(adjust_colors)

    @tool(mutating=True, title="Curves")
    def adjust_curves(document_id: DocId, layer_id: str | None, points: Points | None = None,
                      red: Points | None = None, green: Points | None = None, blue: Points | None = None,
                      as_adjustment_layer: bool = True) -> dict[str, Any]:
        """Tone curves with [input, output] control points in 0..255 (monotone cubic). E.g. gentle S-curve:
        points=[[0,0],[64,54],[192,205],[255,255]]. Per-channel curves for color grading."""
        return ed.adjust_curves(document_id, layer_id, points, red, green, blue, as_adjustment_layer)

    @tool(mutating=True, title="Update adjustment layer")
    def update_adjustment_layer(document_id: DocId, layer_id: LayerId, params: dict[str, Any]) -> dict[str, Any]:
        """Change parameters of an existing adjustment layer (merged with its current params)."""
        return ed.update_adjustment_layer(document_id, layer_id, params)

    @tool(mutating=True, title="Match color")
    def match_color(document_id: DocId, layer_id: LayerId, reference: str = "below", region: Rect | None = None,
                    strength: float = 0.7, preserve_luminance: bool = False,
                    as_adjustment_layer: bool = True) -> dict[str, Any]:
        """Match a composited layer's color statistics (Lab mean/std) to the scene: reference = below (the
        composite around the layer) | region (with region) | another layer id. Creates a clipped adjustment
        layer by default."""
        return ed.match_color(document_id, layer_id, reference, region, strength, preserve_luminance,
                              as_adjustment_layer)

    @tool(mutating=True, title="Blur layer")
    def blur_layer(document_id: DocId, layer_id: LayerId, radius: float = 4.0, method: str = "gaussian",
                   angle: float = 0.0, use_selection: bool = False) -> dict[str, Any]:
        """Blur: gaussian | box | motion (angle in degrees) | lens (bokeh disk). For depth of field use
        apply_filter('gradient_blur') or blur background layers more than foreground ones."""
        return ed.blur_layer(document_id, layer_id, radius, method, angle, use_selection)

    @tool(mutating=True, title="Sharpen layer")
    def sharpen_layer(document_id: DocId, layer_id: LayerId, amount: float = 0.8, radius: float = 1.5,
                      threshold: float = 2.0, use_selection: bool = False) -> dict[str, Any]:
        """Unsharp-mask sharpening (amount 0..5, radius px, threshold 0..255)."""
        return ed.sharpen_layer(document_id, layer_id, amount, radius, threshold, use_selection)

    @tool(mutating=True, title="Clone stamp")
    def clone_stamp(document_id: DocId, layer_id: LayerId, source_point: Point, strokes: Strokes,
                    brush_size: float = 30.0, hardness: float = 0.6, opacity: float = 1.0, aligned: bool = True,
                    sample: str = "layer", backend: str = "auto", use_selection: bool = False) -> dict[str, Any]:
        """Clone stamp: paints pixels sampled at an offset. source_point corresponds to the FIRST point of the
        first stroke; aligned=true keeps that offset for all strokes, false restarts at source_point for each
        stroke. sample = layer | merged (all visible layers) | <layer_id>. Use for retouching and extending
        existing texture, NOT for inventing new objects. backend='gimp' uses GIMP's native clone tool.
        Vary the source between strokes and keep opacity < 1 for organic texture to avoid visible repeats."""
        return ed.clone_stamp(document_id, layer_id, source_point, strokes, brush_size, hardness, opacity, aligned,
                              sample, backend, use_selection)

    @tool(mutating=True, title="Heal region")
    def heal_region(document_id: DocId, layer_id: LayerId, strokes: Strokes, source_point: Point | None = None,
                    brush_size: float = 30.0, hardness: float = 0.5, backend: str = "auto") -> dict[str, Any]:
        """Healing brush. With source_point: copies texture from the source and adapts its color/light to the
        destination (Poisson blending; GIMP heal with backend='gimp'). Without source_point: spot healing that
        reconstructs the stroked area from its surroundings."""
        return ed.heal_region(document_id, layer_id, strokes, source_point, brush_size, hardness, backend)

    @tool(mutating=True, title="Remove object")
    def remove_object(document_id: DocId, layer_id: LayerId, region: str = "selection", rect: Rect | None = None,
                      polygon: Points | None = None, method: str = "telea", dilate: int = 4) -> dict[str, Any]:
        """Remove an object by inpainting the region (selection | rect | polygon) from its surroundings
        (method telea | navier_stokes). Good for small/medium objects; inspect the result and refine large or
        structured areas with clone_stamp / heal_region."""
        return ed.remove_object(document_id, layer_id, region, rect, polygon, method, dilate)

    @tool(mutating=True, title="Remove background")
    def remove_background(document_id: DocId, layer_id: LayerId, method: str = "grabcut", rect: Rect | None = None,
                          foreground_points: Points | None = None, background_points: Points | None = None,
                          color: str | None = None, tolerance: float = 40.0,
                          edge_feather: float = 1.0) -> dict[str, Any]:
        """Hide the background with a LAYER MASK (pixels untouched). method: grabcut (rect around the subject,
        optional foreground/background seed points; good default) | color_key (solid backdrops: color,
        tolerance) | rembg (if installed). Inspect the mask edge afterwards and refine with edit_layer_mask."""
        return ed.remove_background(document_id, layer_id, method, rect, foreground_points, background_points,
                                    color, tolerance, 5, edge_feather)
