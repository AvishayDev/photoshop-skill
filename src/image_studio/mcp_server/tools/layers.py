from __future__ import annotations

from typing import Any

from .common import DocId, LayerId


def register(tool, session) -> None:
    ed = session.editor

    @tool(read_only=True, title="List layers")
    def list_layers(document_id: DocId) -> dict[str, Any]:
        """Layer tree top-to-bottom with ids, kinds, bounds, visibility, opacity, blend modes, masks, depth."""
        return ed.list_layers(document_id)

    @tool(read_only=True, title="Layer info")
    def get_layer_info(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Detailed layer info: opaque bounds (local and document), coverage, mean color, text/shape/fill
        properties, effects, source asset and license."""
        return ed.get_layer_info(document_id, layer_id)

    @tool(mutating=True, title="Create layer")
    def create_layer(document_id: DocId, name: str = "Layer", fill_color: str | None = None,
                     above: str | None = None, position: str | None = None, parent_id: str | None = None,
                     opacity: float = 1.0, blend_mode: str = "normal") -> dict[str, Any]:
        """New canvas-sized raster layer, transparent or filled with fill_color. Placed above layer `above`,
        at position='bottom', inside group parent_id, or on top by default."""
        return ed.create_layer(document_id, name, fill_color, above, parent_id, position, opacity, blend_mode)

    @tool(mutating=True, title="Import image as layer")
    def import_image_as_layer(document_id: DocId, path: str | None = None, reference_id: str | None = None,
                              name: str | None = None, x: int | None = None, y: int | None = None,
                              fit: str = "none", scale: float | None = None, above: str | None = None,
                              license_acknowledged: bool = False) -> dict[str, Any]:
        """Import a local image file or a fetched research reference (reference_id) as a new layer. The
        original is copied to assets/ and recorded with provenance. fit: none | contain | cover | width |
        height; scaled imports stay 'smart' (re-rendered from the original on later transforms). References
        whose license forbids compositing are refused unless license_acknowledged=true. x/y default to centered."""
        return ed.import_image_as_layer(document_id, path, reference_id, name, x, y, fit, scale, above, None,
                                        license_acknowledged)

    @tool(mutating=True, title="Duplicate layer")
    def duplicate_layer(document_id: DocId, layer_id: LayerId, name: str | None = None) -> dict[str, Any]:
        """Duplicate a layer (or group) directly above itself; the copy is unlocked for editing."""
        return ed.duplicate_layer(document_id, layer_id, name)

    @tool(mutating=True, destructive=True, title="Delete layer")
    def delete_layer(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Delete a layer (and a group's children). Recoverable with undo/restore_checkpoint."""
        return ed.delete_layer(document_id, layer_id)

    @tool(mutating=True, title="Rename layer")
    def rename_layer(document_id: DocId, layer_id: LayerId, name: str) -> dict[str, Any]:
        """Rename a layer. Use meaningful names (e.g. 'Tiger', 'Tiger · contact shadow')."""
        return ed.rename_layer(document_id, layer_id, name)

    @tool(mutating=True, title="Move layer in stack")
    def move_layer(document_id: DocId, layer_id: LayerId, position: str = "up",
                   reference_layer_id: str | None = None, group_id: str | None = None) -> dict[str, Any]:
        """Reorder: position = up | down | top | bottom | above | below (needs reference_layer_id) |
        into_group (needs group_id) | out_of_group. To change x/y use set_layer_properties or transform_layer."""
        return ed.move_layer(document_id, layer_id, position, reference_layer_id, group_id)

    @tool(mutating=True, title="Set layer properties")
    def set_layer_properties(document_id: DocId, layer_id: LayerId, name: str | None = None,
                             visible: bool | None = None, opacity: float | None = None,
                             blend_mode: str | None = None, clipped: bool | None = None,
                             locked_pixels: bool | None = None, x: int | None = None,
                             y: int | None = None) -> dict[str, Any]:
        """Set several properties at once. blend_mode: normal multiply screen overlay soft_light hard_light
        darken lighten color_dodge color_burn linear_dodge linear_burn difference exclusion subtract divide hue
        saturation color luminosity (pass_through for groups). clipped=true clips the layer to the one below.
        x/y set the layer's top-left position in document pixels."""
        return ed.set_layer_properties(document_id, layer_id, name=name, visible=visible, opacity=opacity,
                                       blend_mode=blend_mode, clipped=clipped, locked_pixels=locked_pixels, x=x, y=y)

    @tool(mutating=True, title="Set visibility")
    def set_layer_visibility(document_id: DocId, layer_id: LayerId, visible: bool) -> dict[str, Any]:
        """Show or hide a layer."""
        return ed.set_layer_visibility(document_id, layer_id, visible)

    @tool(mutating=True, title="Set opacity")
    def set_layer_opacity(document_id: DocId, layer_id: LayerId, opacity: float) -> dict[str, Any]:
        """Layer opacity in 0..1."""
        return ed.set_layer_opacity(document_id, layer_id, opacity)

    @tool(mutating=True, title="Set blend mode")
    def set_blend_mode(document_id: DocId, layer_id: LayerId, blend_mode: str) -> dict[str, Any]:
        """Set a layer's blend mode (see set_layer_properties for the list)."""
        return ed.set_blend_mode(document_id, layer_id, blend_mode)

    @tool(mutating=True, title="Blend layers")
    def blend_layers(document_id: DocId, top_layer_id: LayerId, blend_mode: str = "normal", opacity: float = 1.0,
                     merge: bool = False) -> dict[str, Any]:
        """Set how a layer blends with the layers below; with merge=true also merge it down (destructive)."""
        return ed.blend_layers(document_id, top_layer_id, blend_mode, opacity, merge)

    @tool(mutating=True, title="Create group")
    def create_group(document_id: DocId, name: str, layer_ids: list[str] | None = None,
                     blend_mode: str = "pass_through") -> dict[str, Any]:
        """Create a layer group, optionally moving sibling layers into it (order preserved)."""
        return ed.create_group(document_id, name, layer_ids, blend_mode)

    @tool(mutating=True, destructive=True, title="Merge down")
    def merge_down(document_id: DocId, layer_id: LayerId, name: str | None = None) -> dict[str, Any]:
        """Merge a layer into the one below (destructive; prefer keeping layers separate)."""
        return ed.merge_down(document_id, layer_id, name)

    @tool(mutating=True, destructive=True, title="Flatten image")
    def flatten_image(document_id: DocId, background: str | None = "#ffffff") -> dict[str, Any]:
        """Flatten everything into one layer. Only when the user explicitly asks; exports never need it."""
        return ed.flatten_image(document_id, background)

    @tool(mutating=True, title="Rasterize layer")
    def rasterize_layer(document_id: DocId, layer_id: LayerId) -> dict[str, Any]:
        """Turn a text/shape/fill/smart layer into plain pixels (needed before pixel retouching)."""
        return ed.rasterize_layer(document_id, layer_id)

    @tool(mutating=True, title="Transform layer")
    def transform_layer(document_id: DocId, layer_id: LayerId, translate_x: float = 0.0, translate_y: float = 0.0,
                        scale_x: float = 1.0, scale_y: float | None = None, rotate: float = 0.0,
                        shear_x: float = 0.0, shear_y: float = 0.0, flip_horizontal: bool = False,
                        flip_vertical: bool = False, pivot: str | list[float] = "center",
                        perspective: list[list[float]] | None = None,
                        interpolation: str = "cubic") -> dict[str, Any]:
        """Move/scale/rotate (degrees, clockwise)/shear/flip about a pivot ('center', 'bottom', 'top_left', ...
        or [x, y]), or map the layer onto 4 perspective corners [[TL],[TR],[BR],[BL]] in document pixels.
        Works on groups (applied to every child). Re-renders from the original pixels to avoid quality loss."""
        return ed.transform_layer(document_id, layer_id, translate_x=translate_x, translate_y=translate_y,
                                  scale_x=scale_x, scale_y=scale_y, rotate=rotate, shear_x=shear_x, shear_y=shear_y,
                                  flip_horizontal=flip_horizontal, flip_vertical=flip_vertical, pivot=pivot,
                                  perspective=perspective, interpolation=interpolation)

    @tool(mutating=True, title="Rotate layer")
    def rotate_layer(document_id: DocId, layer_id: LayerId, angle: float, pivot: str | list[float] = "center"
                     ) -> dict[str, Any]:
        """Rotate a layer by `angle` degrees clockwise about the pivot."""
        return ed.rotate_layer(document_id, layer_id, angle, pivot)

    @tool(mutating=True, title="Flip layer")
    def flip_layer(document_id: DocId, layer_id: LayerId, direction: str = "horizontal") -> dict[str, Any]:
        """Mirror a layer horizontally or vertically about its center."""
        return ed.flip_layer(document_id, layer_id, direction)

    @tool(mutating=True, title="Align layers")
    def align_layers(document_id: DocId, layer_ids: list[str], alignment: str,
                     relative_to: str = "canvas") -> dict[str, Any]:
        """Align layers' visible content: left | center | right | top | middle | bottom, relative to canvas |
        selection | first (the first layer in layer_ids)."""
        return ed.align_layers(document_id, layer_ids, alignment, relative_to)
