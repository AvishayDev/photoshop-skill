"""Layer model.

A layer stores *references* to pixel blobs (content-addressed PNG files), never
the pixels themselves, so documents with many layers stay cheap to load and
snapshot. Pixels are only decoded when an operation needs them.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LayerKind(str, Enum):
    raster = "raster"
    text = "text"
    shape = "shape"
    fill = "fill"
    group = "group"
    adjustment = "adjustment"


class BlendMode(str, Enum):
    normal = "normal"
    multiply = "multiply"
    screen = "screen"
    overlay = "overlay"
    soft_light = "soft_light"
    hard_light = "hard_light"
    darken = "darken"
    lighten = "lighten"
    color_dodge = "color_dodge"
    color_burn = "color_burn"
    linear_dodge = "linear_dodge"
    linear_burn = "linear_burn"
    difference = "difference"
    exclusion = "exclusion"
    subtract = "subtract"
    divide = "divide"
    hue = "hue"
    saturation = "saturation"
    color = "color"
    luminosity = "luminosity"
    pass_through = "pass_through"  # groups only


class MaskRef(BaseModel):
    """Grayscale mask aligned with the layer's pixel bounds (white = visible)."""

    blob: str
    enabled: bool = True


class Effect(BaseModel):
    """Non-destructive layer style rendered at composite time."""

    id: str
    type: str = Field(description="drop_shadow | outer_glow | stroke")
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class TextProps(BaseModel):
    text: str
    font: str = "DejaVu Sans"
    size: float = 48.0
    color: str = "#ffffff"
    align: str = "left"
    line_spacing: float = 1.2
    max_width: int | None = None
    stroke_width: int = 0
    stroke_color: str = "#000000"
    font_path: str | None = None  # resolved font file, recorded for reproducibility


class ShapeProps(BaseModel):
    shape: str = "rectangle"  # rectangle | ellipse | rounded_rectangle | polygon | line
    width: int
    height: int
    points: list[list[float]] | None = None  # polygon / line, local coordinates
    fill: str | None = "#ffffff"
    stroke: str | None = None
    stroke_width: float = 0.0
    corner_radius: float = 0.0


class FillProps(BaseModel):
    type: str = "solid"  # solid | linear_gradient | radial_gradient
    color: str = "#808080"
    stops: list[list[Any]] | None = None  # [[offset 0..1, "#rrggbb[aa]"], ...]
    angle: float = 90.0  # degrees, linear gradients; 90 = top -> bottom
    center: list[float] = Field(default_factory=lambda: [0.5, 0.5])  # radial, normalized
    radius: float = 0.75  # radial, fraction of the canvas diagonal / 2


class AdjustmentProps(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class Layer(BaseModel):
    id: str
    name: str
    kind: LayerKind = LayerKind.raster
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    visible: bool = True
    opacity: float = Field(1.0, ge=0.0, le=1.0)
    blend_mode: BlendMode = BlendMode.normal
    locked_pixels: bool = False
    clipped: bool = Field(False, description="Clipping mask: only visible where the layer below is opaque")
    pixels: str | None = None  # blob hash, RGBA
    mask: MaskRef | None = None
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)  # groups: bottom -> top
    text: TextProps | None = None
    shape: ShapeProps | None = None
    fill: FillProps | None = None
    adjustment: AdjustmentProps | None = None
    effects: list[Effect] = Field(default_factory=list)
    # "Smart" transform: pixels are re-rendered from ``base_blob`` through ``transform``
    # (3x3 matrix, base pixel coords -> document coords) so repeated transforms don't
    # accumulate resampling loss. Cleared when pixels are edited directly.
    base_blob: str | None = None
    transform: list[list[float]] | None = None
    source_asset: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    backend_meta: dict[str, Any] = Field(default_factory=dict)

    def bounds(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "bounds": {"x": self.x, "y": self.y, "width": self.width, "height": self.height},
            "visible": self.visible,
            "opacity": round(self.opacity, 4),
            "blend_mode": self.blend_mode.value,
            "has_mask": self.mask is not None,
            "mask_enabled": bool(self.mask and self.mask.enabled),
            "clipped": self.clipped,
            "locked_pixels": self.locked_pixels,
            "parent_id": self.parent_id,
        }
        if self.kind == LayerKind.group:
            out["children"] = list(self.children)
        if self.text:
            out["text"] = self.text.text
        if self.adjustment:
            out["adjustment"] = self.adjustment.model_dump()
        if self.effects:
            out["effects"] = [e.model_dump() for e in self.effects]
        if self.source_asset:
            out["source_asset"] = self.source_asset
        if self.base_blob:
            out["smart_transform"] = True
        return out
