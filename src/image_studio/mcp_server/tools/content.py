from __future__ import annotations

from typing import Any

from ...core.compositor import EFFECT_DEFAULTS
from ...core.render import PROCEDURAL_KINDS
from .common import DocId, LayerId, Params, Points


def register(tool, session) -> None:
    ed = session.editor

    @tool(mutating=True, title="Create text layer")
    def create_text_layer(document_id: DocId, text: str, x: int = 0, y: int = 0, font: str = "DejaVu Sans",
                          size: float = 48.0, color: str = "#ffffff", align: str = "left",
                          max_width: int | None = None, line_spacing: float = 1.2, stroke_width: int = 0,
                          stroke_color: str = "#000000", name: str | None = None) -> dict[str, Any]:
        """Editable text layer; x, y = top-left. font is a family/style name ('DejaVu Sans Bold') or a .ttf
        path. max_width wraps lines. Edit later with update_text_layer."""
        return ed.create_text_layer(document_id, text, x, y, font, size, color, align, max_width, line_spacing,
                                    stroke_width, stroke_color, name)

    @tool(mutating=True, title="Update text layer")
    def update_text_layer(document_id: DocId, layer_id: LayerId, text: str | None = None, font: str | None = None,
                          size: float | None = None, color: str | None = None, align: str | None = None,
                          max_width: int | None = None, line_spacing: float | None = None,
                          stroke_width: int | None = None, stroke_color: str | None = None) -> dict[str, Any]:
        """Change text-layer properties; the layer is re-rendered (and keeps its transform)."""
        changes = {k: v for k, v in dict(text=text, font=font, size=size, color=color, align=align,
                                         max_width=max_width, line_spacing=line_spacing, stroke_width=stroke_width,
                                         stroke_color=stroke_color).items() if v is not None}
        return ed.update_text_layer(document_id, layer_id, **changes)

    @tool(mutating=True, title="Create shape layer")
    def create_shape_layer(document_id: DocId, shape: str = "rectangle", x: float = 0, y: float = 0,
                           width: float = 100, height: float = 100, points: Points | None = None,
                           fill: str | None = "#ffffff", stroke: str | None = None, stroke_width: float = 0.0,
                           corner_radius: float = 0.0, name: str | None = None) -> dict[str, Any]:
        """Anti-aliased shape layer: rectangle | rounded_rectangle | ellipse | polygon | line (points in
        document coords). fill/stroke colors may include alpha ('#rrggbbaa')."""
        return ed.create_shape_layer(document_id, shape, x, y, width, height, points, fill, stroke, stroke_width,
                                     corner_radius, name)

    @tool(mutating=True, title="Create fill/gradient layer")
    def create_fill_layer(document_id: DocId, type: str = "solid", color: str = "#808080",
                          stops: list[list[Any]] | None = None, angle: float = 90.0, center: list[float] | None = None,
                          radius: float = 0.75, name: str | None = None, opacity: float = 1.0,
                          blend_mode: str = "normal", position: str | None = None) -> dict[str, Any]:
        """Canvas-sized fill: solid | linear_gradient (angle deg, 90 = top->bottom) | radial_gradient (center
        normalized [x,y], radius fraction). stops: [[0.0, '#hex'], [1.0, '#hex']]. position='bottom' puts it
        under everything (backgrounds, skies)."""
        return ed.create_fill_layer(document_id, type, color, stops, angle, center, radius, name, opacity,
                                    blend_mode, None, position)

    def create_procedural_layer(document_id: DocId, kind: str, params: Params = None, name: str | None = None,
                                opacity: float = 1.0, blend_mode: str = "normal") -> dict[str, Any]:
        return ed.create_procedural_layer(document_id, kind, params, name, opacity, blend_mode)
    create_procedural_layer.__doc__ = (
        f"Seeded procedural texture layer, kinds: {', '.join(PROCEDURAL_KINDS)}. Params: clouds(scale, octaves, "
        "color_dark, color_light, seed), fog(density, scale, color, vertical_falloff bottom|top|none, seed), "
        "grain(amount, seed; use blend_mode overlay/soft_light at low opacity), bokeh(count, min_radius, "
        "max_radius, color, softness, seed), sky(top, horizon, horizon_position), water(deep, shallow, scale, seed).")
    tool(mutating=True, title="Procedural layer")(create_procedural_layer)

    def add_layer_effect(document_id: DocId, layer_id: LayerId, effect: str, params: Params = None
                         ) -> dict[str, Any]:
        return ed.add_layer_effect(document_id, layer_id, effect, params)
    add_layer_effect.__doc__ = ("Non-destructive layer style rendered at composite time. Effects and defaults: " +
                                "; ".join(f"{k}: {v}" for k, v in EFFECT_DEFAULTS.items()) +
                                ". direction_deg is where the shadow falls (0 right, 90 down).")
    tool(mutating=True, title="Add layer effect")(add_layer_effect)

    @tool(mutating=True, title="Add drop shadow")
    def add_drop_shadow(document_id: DocId, layer_id: LayerId, direction_deg: float = 45.0, distance: float = 12.0,
                        size: float = 14.0, opacity: float = 0.55, color: str = "#000000",
                        spread: float = 0.0) -> dict[str, Any]:
        """Drop shadow layer style (graphic design). For subjects standing in a scene use add_cast_shadow and
        add_contact_shadow instead, which follow the scene's light and ground plane."""
        return ed.add_drop_shadow(document_id, layer_id, direction_deg=direction_deg, distance=distance, size=size,
                                  opacity=opacity, color=color, spread=spread)

    @tool(mutating=True, title="Remove layer effect")
    def remove_layer_effect(document_id: DocId, layer_id: LayerId, effect_id: str) -> dict[str, Any]:
        """Remove a layer style by its effect id."""
        return ed.remove_layer_effect(document_id, layer_id, effect_id)

    @tool(mutating=True, title="Cast shadow")
    def add_cast_shadow(document_id: DocId, layer_id: LayerId, light_azimuth: float = 225.0,
                        light_elevation: float = 35.0, ground_y: float | None = None, softness: float = 0.5,
                        opacity: float = 0.55, color: str = "#000000") -> dict[str, Any]:
        """Project the subject's silhouette onto a flat ground as a separate multiply layer below it. The
        penumbra softens and fades with distance from the contact point. light_azimuth = where the light
        comes FROM (0 right, 90 front/camera, 180 left, 270 behind; 225 = upper-left behind). Low
        light_elevation = long shadows. ground_y = document y of the contact line."""
        return ed.add_cast_shadow(document_id, layer_id, light_azimuth, light_elevation, ground_y, softness,
                                  opacity, color)

    @tool(mutating=True, title="Contact shadow")
    def add_contact_shadow(document_id: DocId, layer_id: LayerId, ground_y: float | None = None, blur: float = 6.0,
                           spread: float = 0.12, opacity: float = 0.75) -> dict[str, Any]:
        """Dark occlusion where the subject touches the ground (feet, paws, base). Essential for grounding."""
        return ed.add_contact_shadow(document_id, layer_id, ground_y, blur, spread, opacity)

    @tool(mutating=True, title="Reflection")
    def create_reflection(document_id: DocId, layer_id: LayerId, axis_y: float | None = None, opacity: float = 0.6,
                          fade: float = 0.7, blur: float = 2.0, ripple_amplitude: float = 3.0,
                          ripple_wavelength: float = 18.0, squash: float = 1.0, tint: str | None = "#1d4e6b",
                          tint_strength: float = 0.25, darken: float = 0.15, seed: int = 0) -> dict[str, Any]:
        """Water/gloss reflection mirrored about the waterline axis_y (document y; default: subject bottom), with
        Fresnel darkening, water tint, wave distortion (ripple_*), vertical blur and distance fade. For calm
        water use small ripples; for choppy water larger amplitude and shorter fade."""
        return ed.create_reflection(document_id, layer_id, axis_y, opacity, fade, blur, ripple_amplitude,
                                    ripple_wavelength, squash, tint, tint_strength, darken, seed)

    @tool(mutating=True, title="Lighting effect")
    def add_lighting_effect(document_id: DocId, kind: str = "point", x: float = 0.5, y: float = 0.2,
                            color: str = "#ffd9a0", intensity: float = 0.6, radius: float = 0.5,
                            angle: float = 45.0, softness: float = 0.6, blend_mode: str | None = None,
                            layer_id: str | None = None, light_azimuth: float = 225.0, width: float = 4.0,
                            rays_length: float = 0.35, threshold: float = 0.65) -> dict[str, Any]:
        """Light on its own layer: point (glow at normalized x,y; screen) | directional (wash from angle;
        soft_light) | god_rays (crepuscular rays from x,y through bright gaps, e.g. sun through trees) | rim
        (edge light on layer_id from light_azimuth, clipped). Adjust intensity/opacity to taste."""
        return ed.add_lighting_effect(document_id, kind, x, y, color, intensity, radius, angle, softness,
                                      blend_mode, layer_id, light_azimuth, width, rays_length, threshold)
