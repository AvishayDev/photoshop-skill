"""Declarative pipelines: the same painting actions as a JSON spec (used by the MCP ``run_pipeline`` and
``paint_layer`` tools and by ``image-studio pipeline run spec.json``).

Spec::

    {"request": "...", "plan": ["10+ steps"], "size": [1600, 1000], "name": "...", "seed": 3,
     "steps": [
        {"step": 5, "action": "sky", "name": "Sky", "group": "Environment",
         "params": {"horizon_y": 560, "colors": ["#2c4f7c", "#e9b98a"], "sun": [1150, 520]}},
        {"step": 9, "action": "figure", "name": "Tiger", "params": {"spec": "figure/tiger-walking",
         "height": 330, "x": 420, "ground_y": 860, "facing": "right"}},
        {"step": 10, "action": "cast_shadow", "name": "Tiger shadow",
         "params": {"of": "Tiger", "azimuth": 200, "elevation": 30, "opacity": 0.5}},
        {"step": 12, "action": "preview", "params": {"tag": "after-subject"}}
     ]}

Canvas-sized actions receive ``width``/``height`` automatically. Layer options per step: ``name``,
``group``, ``blend``, ``opacity``.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import numpy as np

from ..errors import ValidationError
from ..paint import brush, canvas, finish, patterns, scene, shapes
from .pipeline import Pipeline


def _canvas_action(fn: Callable[..., np.ndarray]) -> Callable[..., list[str]]:
    def run(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
        return [p.add(name, fn(p.width, p.height, **params), **opts)]
    run.__doc__ = inspect.getdoc(fn)
    run._target = fn  # type: ignore[attr-defined]
    return run


def _forest(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    ids = []
    for lname, rgba in scene.forest(p.width, p.height, **params):
        ids.append(p.add(f"{name} · {lname}", rgba, **opts))
    return ids


def _figure(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    params = dict(params)
    spec = params.pop("spec")
    return [p.figure(name, spec, group=opts.get("group"), **params)]


def _pattern(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    """Pattern fill: {"type": "stripes"|"spots", "color": "#hex", "mask_layer": optional layer name, ...}."""
    params = dict(params)
    kind = params.pop("type", "stripes")
    color = params.pop("color", "#111111")
    mask_layer = params.pop("mask_layer", None)
    gen = {"stripes": patterns.stripes, "spots": patterns.spots}.get(kind)
    if gen is None:
        raise ValidationError("pattern type must be stripes or spots")
    m = gen(p.width, p.height, **params)
    if mask_layer:
        m = m * p.layer(mask_layer)[..., 3]
    return [p.add(name, canvas.solid(p.width, p.height, color, m), **opts)]


def _strokes(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    """Brush strokes: {"strokes": [{"points": [[x, y], ...], "color", "size", "hardness", "size_end",
    "opacity"}, ...]}."""
    c = p.blank()
    for s in params.get("strokes", []):
        s = dict(s)
        brush.stroke(c, s.pop("points"), s.pop("color", "#000000"), **s)
    return [p.add(name, c, **opts)]


def _shape(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    """Filled shape: {"shape": "polygon"|"ellipse"|"blob"|"capsule", "color", geometry..., "feather"}."""
    params = dict(params)
    kind = params.pop("shape", "polygon")
    color = params.pop("color", "#000000")
    fn = {"polygon": shapes.polygon, "ellipse": shapes.ellipse, "blob": shapes.blob, "capsule": shapes.capsule,
          "bent_capsule": shapes.bent_capsule}.get(kind)
    if fn is None:
        raise ValidationError("shape must be polygon, ellipse, blob, capsule or bent_capsule")
    m = fn(p.width, p.height, **params)
    return [p.add(name, canvas.solid(p.width, p.height, color, m), **opts)]


def _subject_op(method: str) -> Callable[..., list[str]]:
    def run(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
        kw = dict(params)
        if method != "rim_light" and opts.get("group"):
            kw["group"] = opts["group"]
        return [getattr(p, method)(name, **kw)]
    run.__doc__ = inspect.getdoc(getattr(Pipeline, method))
    return run


def _adjust(p: Pipeline, name: str, params: dict[str, Any], opts: dict[str, Any]) -> list[str]:
    """Adjustment layer: {"adjustment": "curves"|"hue_saturation"|..., "params": {...}, "on": layer name}."""
    return [p.adjust(name, params["adjustment"], params.get("params", {}), on=params.get("on"))]


ACTIONS: dict[str, Callable[..., list[str]]] = {
    "sky": _canvas_action(scene.sky),
    "sun": _canvas_action(scene.sun_disc),
    "clouds": _canvas_action(scene.clouds),
    "mountains": _canvas_action(scene.mountains),
    "ground": _canvas_action(scene.ground),
    "ocean": _canvas_action(scene.ocean),
    "foliage": _canvas_action(scene.foliage),
    "grass": _canvas_action(brush.grass),
    "light_rays": _canvas_action(scene.light_rays),
    "haze": _canvas_action(scene.haze),
    "vignette": _canvas_action(finish.vignette),
    "grain": _canvas_action(finish.grain),
    "wash": _canvas_action(finish.wash),
    "forest": _forest,
    "figure": _figure,
    "pattern": _pattern,
    "strokes": _strokes,
    "shape": _shape,
    "cast_shadow": _subject_op("cast_shadow"),
    "contact_shadow": _subject_op("contact_shadow"),
    "reflection": _subject_op("reflection"),
    "rim_light": _subject_op("rim_light"),
    "adjust": _adjust,
}
_forest.__doc__ = inspect.getdoc(scene.forest)
_figure.__doc__ = inspect.getdoc(Pipeline.figure)


def describe_actions() -> dict[str, Any]:
    out = {}
    for name, fn in ACTIONS.items():
        target = getattr(fn, "_target", None)
        params = {}
        if target is not None:
            for pname, prm in inspect.signature(target).parameters.items():
                if pname in ("width", "height"):
                    continue
                params[pname] = None if prm.default is inspect.Parameter.empty else repr(prm.default)
        out[name] = {"doc": (inspect.getdoc(fn) or "").split("\n\n")[0], "params": params or None}
    out["preview"] = {"doc": "Render the composite so far to previews/ (params: tag).", "params": {"tag": "'stage'"}}
    return out


def run_step(p: Pipeline, step: dict[str, Any]) -> list[str]:
    action = step.get("action")
    if action == "preview":
        return [p.preview(step.get("params", {}).get("tag", f"step{step.get('step', '')}"))]
    if action not in ACTIONS:
        raise ValidationError(f"Unknown pipeline action '{action}'", details={"actions": sorted(ACTIONS)})
    name = step.get("name") or action.replace("_", " ").title()
    opts = {k: step[k] for k in ("group", "blend", "opacity") if k in step}
    try:
        return ACTIONS[action](p, name, dict(step.get("params", {})), opts)
    except TypeError as exc:
        raise ValidationError(f"Bad parameters for action '{action}': {exc}",
                              hint="Call list_paint_actions for the accepted parameters.") from exc


def run_spec(spec: dict[str, Any], *, editor=None, workspace=None, verbose: bool = False) -> dict[str, Any]:
    """Execute a declarative pipeline spec end to end and return the pipeline report."""
    for key in ("request", "plan", "steps"):
        if key not in spec:
            raise ValidationError(f"Pipeline spec needs '{key}'")
    size = spec.get("size", [1600, 1000])
    p = Pipeline(spec["request"], spec["plan"], size=(int(size[0]), int(size[1])), name=spec.get("name"),
                 seed=int(spec.get("seed", 0)), editor=editor, workspace=workspace, verbose=verbose)
    for st in spec["steps"]:
        n = int(st.get("step", 1))
        with p.step(n, st.get("note")):
            run_step(p, st)
    for note in spec.get("notes", []):
        p.note(note)
    return p.finish(tuple(spec.get("formats", ["png"])), save_ora=bool(spec.get("save_ora", True)))
