"""The :class:`Pipeline`: a plan-first, layered, reproducible image build driven by painting actions."""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from ..core import fx
from ..editor import Editor
from ..errors import NotFoundError, ValidationError
from ..paint import canvas, figure
from ..workflows.planning import Plan, make_plan


class Pipeline:
    """Build an image from scratch as a layered project, following a mandatory plan of >= 10 steps.

    Every ``add``/``figure``/``shadow``... call becomes a named raster layer (or adjustment layer) in a real
    project under ``projects/<name>/``, so the result stays editable with all image-studio tools. ``step``
    ties layers to the plan step that produced them; ``preview`` renders what exists so far (look at it!);
    ``finish`` exports, writes ``pipeline.json`` (plan, steps, layers, timings, script) and prints a report.
    """

    def __init__(self, request: str, plan: list[str], *, size: tuple[int, int] = (1600, 1000),
                 name: str | None = None, seed: int = 0, editor: Editor | None = None,
                 workspace: str | Path | None = None, background: str | None = None, verbose: bool = True):
        self.plan: Plan
        self.plan, self.plan_warnings = make_plan(request, plan)
        self.editor = editor or Editor(Path(workspace) if workspace else None)
        self.width, self.height = int(size[0]), int(size[1])
        self.seed = int(seed)
        self.verbose = verbose
        res = self.editor.create_project(name or request[:60], self.width, self.height, background=background)
        self.document_id: str = res["document_id"]
        self.project = self.editor.project(self.document_id)
        self.plan.document_id = self.document_id
        (self.project.root / "plans" / f"{self.plan.id}.json").write_text(
            json.dumps(self.plan.model_dump(), indent=1, ensure_ascii=False), encoding="utf-8")
        self.project.manifest.plans.append(self.plan.id)
        self.project.save()
        self.layers: dict[str, str] = {}
        self.groups: dict[str, str] = {}
        self.log: list[dict[str, Any]] = []
        self.previews: list[str] = []
        self.notes: list[str] = []
        self.current_step: int | None = None
        self._layer_log: list[dict[str, Any]] = []
        self._t0 = time.time()
        self._say(self.plan.as_markdown())
        for w in self.plan_warnings:
            self._say(f"plan warning: {w}")

    @classmethod
    def attach(cls, document_id: str, editor: Editor, *, seed: int = 0, verbose: bool = False) -> Pipeline:
        """Paint into an existing document (used by the MCP ``paint_layer`` tool). Layers are addressed by
        name; the plan gate is enforced by the MCP session instead of here."""
        self = cls.__new__(cls)
        self.editor = editor
        self.document_id = document_id
        self.project = editor.project(document_id)
        doc = self.project.doc
        self.width, self.height = doc.width, doc.height
        self.seed, self.verbose = int(seed), verbose
        self.plan, self.plan_warnings = None, []  # type: ignore[assignment]
        self.layers = {lyr.name: lyr.id for lyr in doc.layers.values() if lyr.kind.value != "group"}
        self.groups = {lyr.name: lyr.id for lyr in doc.layers.values() if lyr.kind.value == "group"}
        self.log, self.previews, self.notes = [], [], []
        self.current_step = None
        self._layer_log = []
        self._t0 = time.time()
        return self

    # ----- helpers -------------------------------------------------------------------------------
    def _say(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def rng(self, salt: int = 0) -> np.random.Generator:
        return np.random.default_rng(self.seed * 1000 + salt)

    def blank(self) -> np.ndarray:
        return canvas.blank(self.width, self.height)

    @contextlib.contextmanager
    def step(self, number: int, note: str | None = None):
        """Mark the plan step being executed; layers created inside are tagged with it."""
        if self.plan is None:
            raise ValidationError("This pipeline is attached to an existing document and has no plan steps")
        if not 1 <= number <= len(self.plan.steps):
            raise ValidationError(f"Step {number} is not in the plan (1..{len(self.plan.steps)})")
        prev, self.current_step = self.current_step, number
        t = time.time()
        self._say(f"\n[step {number}/{len(self.plan.steps)}] {self.plan.steps[number - 1].text}"
                  + (f"  -- {note}" if note else ""))
        try:
            yield self
        finally:
            self.log.append({"step": number, "note": note, "seconds": round(time.time() - t, 2),
                             "layers": [e["layer"] for e in self.log_layers if e["step"] == number]})
            self.current_step = prev

    @property
    def log_layers(self) -> list[dict[str, Any]]:
        return list(self._layer_log)

    def _record(self, name: str, layer_id: str, kind: str) -> None:
        self._layer_log.append({"step": self.current_step, "layer": name, "layer_id": layer_id, "kind": kind})
        self.layers[name] = layer_id

    def group(self, name: str) -> str:
        """Get or create a layer group (folder) by name."""
        if name not in self.groups:
            res = self.editor.create_group(self.document_id, name)
            self.groups[name] = res["group_id"]
        return self.groups[name]

    # ----- layers --------------------------------------------------------------------------------
    def add(self, name: str, rgba: np.ndarray, *, group: str | None = None, blend: str = "normal",
            opacity: float = 1.0, x: int = 0, y: int = 0, clipped: bool = False,
            meta: dict[str, Any] | None = None) -> str:
        """Add a painted float/uint8 RGBA image as a new named layer (top of the stack or of ``group``)."""
        if name in self.layers:
            raise ValidationError(f"A layer named '{name}' already exists in this document; use unique names")
        arr = rgba if rgba.dtype == np.uint8 else canvas.to_u8(rgba)
        res = self.editor.add_pixel_layer(self.document_id, arr, name, x=x, y=y, opacity=opacity, blend_mode=blend,
                                          parent_id=self.group(group) if group else None, clipped=clipped,
                                          metadata={"plan_step": self.current_step, **(meta or {})})
        self._record(name, res["layer_id"], "paint")
        self._say(f"  + layer '{name}'" + (f" [{blend} {opacity:.2f}]" if blend != "normal" or opacity < 1 else ""))
        return res["layer_id"]

    def adjust(self, name: str, adjustment: str, params: dict[str, Any], *, on: str | None = None) -> str:
        """Non-destructive adjustment layer (curves, hue_saturation, color_balance, levels, ...). With ``on``
        it is clipped to that layer; otherwise it affects everything below it."""
        res = self.editor.adjust_colors(self.document_id, self.layers[on] if on else None, adjustment, params,
                                        as_adjustment_layer=True, clipped=bool(on), name=name)
        self._record(name, res["layer_id"], "adjustment")
        self._say(f"  + adjustment '{name}' ({adjustment})")
        return res["layer_id"]

    def layer(self, name: str) -> np.ndarray:
        """Full-canvas float RGBA of a named layer (mask applied)."""
        if name not in self.layers:
            raise NotFoundError(f"No pipeline layer '{name}'", details={"layers": list(self.layers)})
        lyr = self.project.doc.layer(self.layers[name])
        px = canvas.from_u8(self.editor.pixels(self.project, lyr))
        if lyr.mask and lyr.mask.enabled:
            px[..., 3] *= canvas.from_u8(self.project.blobs.get(lyr.mask.blob))
        return canvas.place(px, self.width, self.height, lyr.x, lyr.y)

    def composite(self) -> np.ndarray:
        """Current flattened image (float RGBA) - e.g. to sample colours or build reflections."""
        return self.editor.render_doc(self.project)

    # ----- subjects ------------------------------------------------------------------------------
    def figure(self, name: str, spec: dict[str, Any] | str, *, height: float, x: float, ground_y: float,
               facing: str = "left", light_azimuth: float = 200.0, light_elevation: float = 40.0,
               key_color: str = "#fff2dc", ambient_color: str = "#93a8c4", ambient: float = 0.35,
               group: str | None = None, **overrides: Any) -> str:
        """Render a figure spec (dict, or a pattern-library id such as 'figure/tiger-walking') as a layer.
        ``x`` = left edge of the figure box, ``ground_y`` = where its feet touch the ground."""
        if isinstance(spec, str):
            from ..patterns.library import PatternLibrary
            spec = PatternLibrary().get(spec).params
        if overrides:
            spec = {**spec, **overrides}
        fig = figure.render_figure(spec, height=height, light_azimuth=light_azimuth, light_elevation=light_elevation,
                                   key_color=key_color, ambient_color=ambient_color, ambient=ambient, facing=facing,
                                   seed=self.seed)
        pad = int(height * 0.06) + 4
        return self.add(name, fig, group=group, x=int(round(x)) - pad, y=int(round(ground_y - height)) - pad,
                        meta={"figure": spec.get("title", "figure"), "height": height, "facing": facing})

    # ----- light interaction ------------------------------------------------------------------
    def cast_shadow(self, name: str, of: str, *, azimuth: float, elevation: float, ground_y: float | None = None,
                    opacity: float = 0.5, softness: float = 0.5, color: str = "#000000",
                    group: str | None = None) -> str:
        """Shadow of layer ``of`` projected on the ground away from the light (multiply layer)."""
        a = self.layer(of)[..., 3]
        arr, ox, oy = fx.cast_shadow(a, light_azimuth=azimuth, light_elevation=elevation, ground_y=ground_y,
                                     softness=softness, color=color, opacity=1.0)
        return self._add_u8(name, arr, ox, oy, blend="multiply", opacity=opacity, group=group)

    def contact_shadow(self, name: str, of: str, *, ground_y: float | None = None, blur: float = 6.0,
                       spread: float = 0.12, opacity: float = 0.7, group: str | None = None) -> str:
        a = self.layer(of)[..., 3]
        arr, ox, oy = fx.contact_shadow(a, ground_y=ground_y, blur=blur, spread=spread, opacity=1.0, color="#000000")
        return self._add_u8(name, arr, ox, oy, blend="multiply", opacity=opacity, group=group)

    def reflection(self, name: str, of: str, *, axis_y: float, opacity: float = 0.55, fade: float = 0.7,
                   blur: float = 2.0, ripple_amplitude: float = 3.0, ripple_wavelength: float = 18.0,
                   tint: str | None = "#1d4e6b", tint_strength: float = 0.25, darken: float = 0.15,
                   group: str | None = None) -> str:
        """Mirror layer ``of`` about the waterline ``axis_y`` with Fresnel darkening, tint and ripples."""
        src = canvas.to_u8(self.layer(of))
        arr, ox, oy = fx.reflection(src, axis_y=axis_y, fade=fade, opacity=1.0, blur=blur,
                                    ripple_amplitude=ripple_amplitude, ripple_wavelength=ripple_wavelength,
                                    tint=tint, tint_strength=tint_strength, darken=darken, seed=self.seed)
        return self._add_u8(name, arr, ox, oy, opacity=opacity, group=group)

    def rim_light(self, name: str, of: str, *, azimuth: float, width: float = 4.0, color: str = "#ffe2b0",
                  intensity: float = 0.7) -> str:
        """Edge light on ``of`` from the light side, clipped to it (screen)."""
        src = canvas.to_u8(self.layer(of))
        arr = fx.rim_light(src, light_azimuth=azimuth, width=width, color=color, intensity=intensity)
        lid = self.layers[of]
        top = self.editor.clip_stack_top(self.project.doc, lid)
        lyr = self.project.doc.layer(lid)
        res = self.editor.add_pixel_layer(self.document_id, arr, name, opacity=1.0, blend_mode="screen",
                                          parent_id=lyr.parent_id, clipped=True,
                                          metadata={"plan_step": self.current_step, "subject": of})
        # keep the clipped layer directly above its base
        self.editor.move_layer(self.document_id, res["layer_id"], position="above", reference_layer_id=top)
        self._record(name, res["layer_id"], "paint")
        self._say(f"  + rim light '{name}' clipped to '{of}'")
        return res["layer_id"]

    def _add_u8(self, name: str, arr: np.ndarray, ox: int, oy: int, *, blend: str = "normal", opacity: float = 1.0,
                group: str | None = None) -> str:
        return self.add(name, arr, x=ox, y=oy, blend=blend, opacity=opacity, group=group)

    # ----- output --------------------------------------------------------------------------------
    def preview(self, tag: str, max_size: int = 1200) -> str:
        """Render the current composite to previews/stage_<tag>.png. LOOK at it before continuing."""
        res = self.editor.render_preview(self.document_id, max_size=max_size, background="#000000")
        src = Path(res["preview_path"])
        dst = src.with_name(f"stage_{len(self.previews) + 1:02d}_{tag}.png")
        src.replace(dst)
        self.previews.append(str(dst))
        self._say(f"  preview -> {dst}")
        return str(dst)

    def note(self, text: str) -> None:
        """Record an observation/decision (appears in pipeline.json and the final report)."""
        self.notes.append(text)

    def finish(self, formats: tuple[str, ...] = ("png", "jpeg"), save_ora: bool = True) -> dict[str, Any]:
        """Export, save the layered file, write pipeline.json, print and return the report."""
        exports = []
        for fmt in formats:
            exports.append(self.editor.export_image(self.document_id, format=fmt)["export_path"])
        layered = None
        if save_ora:
            layered = self.editor.save_document(self.document_id, format="ora").get("native_file")
        final_preview = self.preview("final")
        report = {
            "request": self.plan.request,
            "project_path": str(self.project.root),
            "document_id": self.document_id,
            "exports": exports,
            "layered_file": layered,
            "final_preview": final_preview,
            "previews": self.previews,
            "plan": [s.text for s in self.plan.steps],
            "steps_executed": sorted({e["step"] for e in self.log} |
                                     ({self.current_step} if self.current_step else set())),
            "steps": self.log,
            "layers": self.log_layers,
            "notes": self.notes,
            "seed": self.seed,
            "size": [self.width, self.height],
            "script": str(Path(sys.argv[0]).resolve()) if sys.argv and sys.argv[0] else None,
            "seconds": round(time.time() - self._t0, 1),
            "method": "procedural painting (image_studio.paint) - no generative model",
        }
        missing = [i + 1 for i in range(len(self.plan.steps)) if i + 1 not in report["steps_executed"]]
        if missing:
            report["plan_steps_not_marked"] = missing
        (self.project.root / "pipeline.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                                         encoding="utf-8")
        self.plan.status = "completed"
        (self.project.root / "plans" / f"{self.plan.id}.json").write_text(
            json.dumps(self.plan.model_dump(), indent=1, ensure_ascii=False), encoding="utf-8")
        self._say("\n== done ==")
        for k in ("project_path", "exports", "layered_file", "final_preview", "seconds"):
            self._say(f"{k}: {report[k]}")
        if missing:
            self._say(f"note: plan steps without a `with p.step(n)` block: {missing}")
        return report
