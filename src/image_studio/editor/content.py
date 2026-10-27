"""Content creation: text, shapes, fills, procedural textures, effects, shadows, reflections, light."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..core import fx, geometry, render
from ..core.color import parse_color, u8_to_f
from ..core.compositor import validate_effect
from ..core.ids import new_id
from ..core.layer import BlendMode, Effect, FillProps, Layer, LayerKind, MaskRef, ShapeProps, TextProps
from ..core.provenance import Provenance
from ..errors import NotFoundError, ValidationError
from .base import EditorBase


class ContentOps(EditorBase):
    def _new_layer(self, proj, tx, layer: Layer, arr: np.ndarray, above: str | None,
                   below: str | None = None) -> None:
        layer.pixels = proj.blobs.put(arr)
        layer.height, layer.width = arr.shape[:2]
        if below:
            ref = tx.doc.layer(below)
            stack = tx.doc.siblings(ref)
            tx.doc.insert(layer, parent_id=ref.parent_id, index=stack.index(below))
        elif above:
            ref = tx.doc.layer(above)
            tx.doc.insert(layer, parent_id=ref.parent_id, above=above)
        else:
            tx.doc.insert(layer)
        tx.touch(layer.id)
        tx.result["layer_id"] = layer.id

    def _rerender(self, proj, layer: Layer, base: np.ndarray) -> None:
        if layer.transform:
            arr, x, y = geometry.warp(base, np.array(layer.transform), "cubic")
            layer.base_blob = proj.blobs.put(base)
            layer.x, layer.y = x, y
        else:
            arr = base
        layer.pixels = proj.blobs.put(arr)
        layer.height, layer.width = arr.shape[:2]

    # ----- text ----------------------------------------------------------------------------
    def create_text_layer(self, document_id: str, text: str, x: int = 0, y: int = 0, font: str = "DejaVu Sans",
                          size: float = 48.0, color: str = "#ffffff", align: str = "left",
                          max_width: int | None = None, line_spacing: float = 1.2, stroke_width: int = 0,
                          stroke_color: str = "#000000", name: str | None = None,
                          above: str | None = None) -> dict[str, Any]:
        """Editable text layer (re-rendered when its properties change). x, y = top-left in document coords."""
        proj = self.project(document_id)
        if align not in ("left", "center", "right"):
            raise ValidationError("align must be left, center or right")
        if not 1 <= size <= 2000:
            raise ValidationError("size must be within 1..2000 px")
        props = TextProps(text=text, font=font, size=size, color=color, align=align, max_width=max_width,
                          line_spacing=line_spacing, stroke_width=stroke_width, stroke_color=stroke_color)
        arr, font_path = render.render_text(props)
        props.font_path = font_path
        with proj.transaction("create_text_layer", {"text": text, "font": font, "size": size, "x": x, "y": y}) as tx:
            layer = Layer(id=new_id("txt"), name=name or text.splitlines()[0][:40], kind=LayerKind.text, x=x, y=y,
                          text=props)
            self._new_layer(proj, tx, layer, arr, above)
            if font_path is None:
                tx.warnings.append("No TrueType font found; used Pillow's built-in font")
            tx.result["font_file"] = font_path
        return self.result(proj, tx)

    def update_text_layer(self, document_id: str, layer_id: str, **changes) -> dict[str, Any]:
        proj = self.project(document_id)
        allowed = set(TextProps.model_fields) - {"font_path"}
        bad = set(changes) - allowed
        if bad:
            raise ValidationError(f"Unknown text properties: {sorted(bad)}", details={"allowed": sorted(allowed)})
        with proj.transaction("update_text_layer", {"layer_id": layer_id, **changes}) as tx:
            layer = tx.doc.layer(layer_id)
            if layer.kind != LayerKind.text or not layer.text:
                raise ValidationError("Layer is not a text layer")
            data = {**layer.text.model_dump(), **{k: v for k, v in changes.items() if v is not None}}
            if "font" in changes:
                data["font_path"] = None
            props = TextProps(**data)
            arr, props.font_path = render.render_text(props)
            layer.text = props
            if layer.mask:
                tx.warnings.append("Text size changed; its mask was removed")
                layer.mask = None
            self._rerender(proj, layer, arr)
            tx.touch(layer_id)
        return self.result(proj, tx)

    # ----- shapes & fills ---------------------------------------------------------------------
    def create_shape_layer(self, document_id: str, shape: str = "rectangle", x: float = 0, y: float = 0,
                           width: float = 100, height: float = 100, points: list[list[float]] | None = None,
                           fill: str | None = "#ffffff", stroke: str | None = None, stroke_width: float = 0.0,
                           corner_radius: float = 0.0, name: str | None = None,
                           above: str | None = None) -> dict[str, Any]:
        """Vector-style shape layer: rectangle | rounded_rectangle | ellipse | polygon | line.
        For polygon/line, points are document coords and x/y/width/height are derived."""
        proj = self.project(document_id)
        if points:
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            x, y = min(xs), min(ys)
            width, height = max(1, max(xs) - x), max(1, max(ys) - y)
            points = [[p[0] - x, p[1] - y] for p in points]
        props = ShapeProps(shape=shape, width=int(round(width)), height=int(round(height)), points=points, fill=fill,
                           stroke=stroke, stroke_width=stroke_width, corner_radius=corner_radius)
        arr = render.render_shape(props)
        pad = int(np.ceil(stroke_width / 2)) + 1
        with proj.transaction("create_shape_layer", {"shape": shape, "x": x, "y": y, "width": width,
                                                     "height": height}) as tx:
            layer = Layer(id=new_id("shp"), name=name or shape.replace("_", " ").title(), kind=LayerKind.shape,
                          x=int(round(x)) - pad, y=int(round(y)) - pad, shape=props)
            self._new_layer(proj, tx, layer, arr, above)
        return self.result(proj, tx)

    def create_fill_layer(self, document_id: str, type: str = "solid", color: str = "#808080",
                          stops: list[list[Any]] | None = None, angle: float = 90.0,
                          center: list[float] | None = None, radius: float = 0.75, name: str | None = None,
                          opacity: float = 1.0, blend_mode: str = "normal", above: str | None = None,
                          position: str | None = None) -> dict[str, Any]:
        """Canvas-sized solid or gradient layer (linear_gradient | radial_gradient). Stops: [[0..1, '#hex'], ...]."""
        proj = self.project(document_id)
        props = FillProps(type=type, color=color, stops=stops, angle=angle, center=center or [0.5, 0.5], radius=radius)
        doc = proj.doc
        arr = render.render_fill(props, doc.width, doc.height)
        with proj.transaction("create_fill_layer", {"type": type, "color": color, "stops": stops}) as tx:
            layer = Layer(id=new_id("fil"), name=name or type.replace("_", " ").title(), kind=LayerKind.fill,
                          fill=props, opacity=opacity, blend_mode=BlendMode(blend_mode))
            if position == "bottom":
                layer.pixels = proj.blobs.put(arr)
                layer.height, layer.width = arr.shape[:2]
                tx.doc.insert(layer, index=0)
                tx.touch(layer.id)
                tx.result["layer_id"] = layer.id
            else:
                self._new_layer(proj, tx, layer, arr, above)
        return self.result(proj, tx)

    def create_procedural_layer(self, document_id: str, kind: str, params: dict[str, Any] | None = None,
                                name: str | None = None, opacity: float = 1.0, blend_mode: str = "normal",
                                above: str | None = None) -> dict[str, Any]:
        """Procedural texture layer: clouds | fog | grain | bokeh | sky | water (seeded, reproducible)."""
        proj = self.project(document_id)
        doc = proj.doc
        arr = render.procedural(kind, doc.width, doc.height, params or {})
        with proj.transaction("create_procedural_layer", {"kind": kind, "params": params or {}}) as tx:
            layer = Layer(id=new_id("prc"), name=name or kind.title(), opacity=opacity,
                          blend_mode=BlendMode(blend_mode), metadata={"procedural": {"kind": kind, **(params or {})}})
            self._new_layer(proj, tx, layer, arr, above)
        return self.result(proj, tx)

    # ----- layer effects ------------------------------------------------------------------------
    def add_layer_effect(self, document_id: str, layer_id: str, effect: str, params: dict[str, Any] | None = None
                         ) -> dict[str, Any]:
        """Non-destructive layer style: drop_shadow | outer_glow | stroke."""
        proj = self.project(document_id)
        clean = validate_effect(effect, params or {})
        with proj.transaction("add_layer_effect", {"layer_id": layer_id, "effect": effect, "params": clean}) as tx:
            layer = tx.doc.layer(layer_id)
            if layer.kind in (LayerKind.group, LayerKind.adjustment):
                raise ValidationError("Effects apply to pixel layers")
            eff = Effect(id=new_id("fx"), type=effect, params={k: v for k, v in clean.items()})
            layer.effects.append(eff)
            tx.touch(layer_id)
            tx.result["effect_id"] = eff.id
        return self.result(proj, tx)

    def add_drop_shadow(self, document_id: str, layer_id: str, **params) -> dict[str, Any]:
        return self.add_layer_effect(document_id, layer_id, "drop_shadow", params)

    def remove_layer_effect(self, document_id: str, layer_id: str, effect_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("remove_layer_effect", {"layer_id": layer_id, "effect_id": effect_id}) as tx:
            layer = tx.doc.layer(layer_id)
            n = len(layer.effects)
            layer.effects = [e for e in layer.effects if e.id != effect_id]
            if len(layer.effects) == n:
                raise NotFoundError(f"No effect '{effect_id}' on this layer")
            tx.touch(layer_id)
        return self.result(proj, tx)

    # ----- physically-motivated helpers -----------------------------------------------------------
    def _subject_alpha(self, proj, layer: Layer) -> np.ndarray:
        rgba = u8_to_f(self.pixels(proj, layer))
        a = rgba[..., 3]
        if layer.mask and layer.mask.enabled:
            a = a * u8_to_f(proj.blobs.get(layer.mask.blob))
        return a

    def add_cast_shadow(self, document_id: str, layer_id: str, light_azimuth: float = 225.0,
                        light_elevation: float = 35.0, ground_y: float | None = None, softness: float = 0.5,
                        opacity: float = 0.55, color: str = "#000000", name: str | None = None) -> dict[str, Any]:
        """Project the subject's silhouette onto the ground as a separate multiply layer below it.
        light_azimuth: where the light comes FROM (0 right, 90 front/camera, 180 left, 270 behind).
        ground_y: document y of the contact line (default: lowest subject pixel)."""
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        local_ground = None if ground_y is None else ground_y - layer.y
        arr, ox, oy = fx.cast_shadow(self._subject_alpha(proj, layer), light_azimuth=light_azimuth,
                                     light_elevation=light_elevation, ground_y=local_ground, softness=softness,
                                     color=color, opacity=1.0)
        with proj.transaction("add_cast_shadow", {"layer_id": layer_id, "light_azimuth": light_azimuth,
                                                  "light_elevation": light_elevation, "ground_y": ground_y}) as tx:
            sh = Layer(id=new_id("shd"), name=name or f"{layer.name} · cast shadow", x=layer.x + ox, y=layer.y + oy,
                       opacity=opacity, blend_mode=BlendMode.multiply,
                       metadata={"generated_by": "add_cast_shadow", "subject": layer_id,
                                 "light_azimuth": light_azimuth, "light_elevation": light_elevation})
            self._new_layer(proj, tx, sh, arr, None, below=layer_id)
        return self.result(proj, tx)

    def add_contact_shadow(self, document_id: str, layer_id: str, ground_y: float | None = None,
                           blur: float = 6.0, spread: float = 0.12, opacity: float = 0.75,
                           color: str = "#000000") -> dict[str, Any]:
        """Tight, dark occlusion shadow where the subject touches the ground (separate multiply layer)."""
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        lg = None if ground_y is None else ground_y - layer.y
        arr, ox, oy = fx.contact_shadow(self._subject_alpha(proj, layer), ground_y=lg, blur=blur, spread=spread,
                                        opacity=1.0, color=color)
        with proj.transaction("add_contact_shadow", {"layer_id": layer_id, "ground_y": ground_y}) as tx:
            sh = Layer(id=new_id("shd"), name=f"{layer.name} · contact shadow", x=layer.x + ox, y=layer.y + oy,
                       opacity=opacity, blend_mode=BlendMode.multiply,
                       metadata={"generated_by": "add_contact_shadow", "subject": layer_id})
            self._new_layer(proj, tx, sh, arr, None, below=layer_id)
        return self.result(proj, tx)

    def create_reflection(self, document_id: str, layer_id: str, axis_y: float | None = None,
                          opacity: float = 0.6, fade: float = 0.7, blur: float = 2.0, ripple_amplitude: float = 3.0,
                          ripple_wavelength: float = 18.0, squash: float = 1.0, tint: str | None = "#1d4e6b",
                          tint_strength: float = 0.25, darken: float = 0.15, seed: int = 0) -> dict[str, Any]:
        """Mirror a subject about a waterline (document y) into a new reflection layer below it, with
        Fresnel darkening, tint, wave distortion and distance fade. Use a mask to hide parts occluded by waves."""
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        rgba = self.pixels(proj, layer).copy()
        if layer.mask and layer.mask.enabled:
            rgba[..., 3] = (rgba[..., 3].astype(np.float32) * u8_to_f(proj.blobs.get(layer.mask.blob)) + 0.5
                            ).astype(np.uint8)
        local_axis = None if axis_y is None else axis_y - layer.y
        arr, ox, oy = fx.reflection(rgba, axis_y=local_axis, fade=fade, opacity=1.0, blur=blur,
                                    ripple_amplitude=ripple_amplitude, ripple_wavelength=ripple_wavelength,
                                    squash=squash, tint=tint, tint_strength=tint_strength, darken=darken, seed=seed)
        with proj.transaction("create_reflection", {"layer_id": layer_id, "axis_y": axis_y, "opacity": opacity,
                                                    "fade": fade, "ripple_amplitude": ripple_amplitude}) as tx:
            rl = Layer(id=new_id("rfl"), name=f"{layer.name} · reflection", x=layer.x + ox, y=layer.y + oy,
                       opacity=opacity, metadata={"generated_by": "create_reflection", "subject": layer_id})
            self._new_layer(proj, tx, rl, arr, None, below=layer_id)
        return self.result(proj, tx)

    def add_lighting_effect(self, document_id: str, kind: str = "point", x: float = 0.5, y: float = 0.2,
                            color: str = "#ffd9a0", intensity: float = 0.6, radius: float = 0.5, angle: float = 45.0,
                            softness: float = 0.6, blend_mode: str | None = None, layer_id: str | None = None,
                            light_azimuth: float = 225.0, width: float = 4.0, rays_length: float = 0.35,
                            threshold: float = 0.65, name: str | None = None) -> dict[str, Any]:
        """Add light as a separate layer. kind = point (glow at normalized x,y) | directional (wash from
        `angle`) | god_rays (rays from x,y through bright gaps of the current composite) | rim (edge light on
        ``layer_id`` from ``light_azimuth``, clipped to it)."""
        proj = self.project(document_id)
        doc = proj.doc
        parse_color(color)
        if kind == "rim":
            if not layer_id:
                raise ValidationError("rim light needs layer_id")
            subject = doc.layer(layer_id)
            rgba = self.pixels(proj, subject).copy()
            if subject.mask and subject.mask.enabled:
                rgba[..., 3] = (rgba[..., 3] * u8_to_f(proj.blobs.get(subject.mask.blob))).astype(np.uint8)
            arr = fx.rim_light(rgba, light_azimuth=light_azimuth, width=width, color=color, intensity=intensity)
            with proj.transaction("add_lighting_effect", {"kind": kind, "layer_id": layer_id,
                                                          "light_azimuth": light_azimuth}) as tx:
                lyr = Layer(id=new_id("lgt"), name=name or f"{subject.name} · rim light", x=subject.x, y=subject.y,
                            blend_mode=BlendMode(blend_mode or "screen"), clipped=True,
                            metadata={"generated_by": "add_lighting_effect", "kind": kind})
                self._new_layer(proj, tx, lyr, arr, self.clip_stack_top(tx.doc, layer_id))
            return self.result(proj, tx)
        backdrop = self.render_doc(proj) if kind == "god_rays" else None
        arr = fx.light_layer(doc.width, doc.height, kind, x=x, y=y, color=color, intensity=intensity, radius=radius,
                             angle=angle, softness=softness, backdrop=backdrop, rays_length=rays_length,
                             threshold=threshold)
        default_mode = {"point": "screen", "directional": "soft_light", "god_rays": "screen"}[kind]
        with proj.transaction("add_lighting_effect", {"kind": kind, "x": x, "y": y, "color": color,
                                                      "intensity": intensity}) as tx:
            lyr = Layer(id=new_id("lgt"), name=name or f"Light · {kind.replace('_', ' ')}",
                        blend_mode=BlendMode(blend_mode or default_mode),
                        metadata={"generated_by": "add_lighting_effect", "kind": kind})
            self._new_layer(proj, tx, lyr, arr, None)
        return self.result(proj, tx)

    # ----- generative ------------------------------------------------------------------------------
    def generate_image_layer(self, document_id: str, prompt: str, negative_prompt: str = "",
                             width: int | None = None, height: int | None = None, seed: int | None = None,
                             provider: str = "comfyui", steps: int = 25, cfg: float = 6.5,
                             name: str | None = None, x: int = 0, y: int = 0,
                             mask_from_selection: bool = False) -> dict[str, Any]:
        """Generate pixels with an optional local generative provider and add them as a new layer.
        With mask_from_selection=true the new layer is masked to the current selection (inpaint-style)."""
        from ..generation import get_generator
        proj = self.project(document_id)
        doc = proj.doc
        gen = get_generator(provider)
        w, h = width or doc.width, height or doc.height
        rgba, meta = gen.generate(prompt=prompt, negative_prompt=negative_prompt, width=w, height=h, seed=seed,
                                  steps=steps, cfg=cfg)
        with proj.transaction("generate_image_layer", {"prompt": prompt, "provider": provider, "seed": meta.get("seed"),
                                                       "width": w, "height": h}) as tx:
            asset = self._add_asset(proj, tx, rgba, None, kind="generated",
                                    provenance=Provenance(origin="generated", provider=provider, generator=meta))
            lyr = Layer(id=new_id("gen"), name=name or f"Generated: {prompt[:30]}", x=x, y=y, source_asset=asset.id,
                        metadata={"prompt": prompt, "negative_prompt": negative_prompt, **meta})
            self._new_layer(proj, tx, lyr, rgba, None)
            if mask_from_selection:
                s = self.doc_mask_to_layer(self.selection_doc(proj, tx.doc), lyr)
                lyr.mask = MaskRef(blob=proj.blobs.put(np.clip(s * 255 + 0.5, 0, 255).astype(np.uint8)))
            tx.result.update(asset_id=asset.id, generator=meta)
        return self.result(proj, tx)
