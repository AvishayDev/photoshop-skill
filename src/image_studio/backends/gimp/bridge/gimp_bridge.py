"""Runs *inside* GIMP 3.x (python-fu-eval batch interpreter).

Usage (performed by image_studio.backends.gimp.backend):

    gimp -i --batch-interpreter=python-fu-eval -b - --quit  < bootstrap

The bootstrap sets ``IMAGE_STUDIO_JOB`` to a JSON job file and executes this
file. The job lists operations from a fixed allow-list; nothing in the job is
ever evaluated as code. Results (or errors) are written to ``result.json`` next
to the job file.

This file deliberately has no dependency on the image_studio package, because
it runs in GIMP's bundled Python interpreter.
"""

import json
import os
import traceback

import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gio  # noqa: E402

RUN = Gimp.RunMode.NONINTERACTIVE

BLEND_MODES = {
    "normal": "NORMAL", "multiply": "MULTIPLY", "screen": "SCREEN", "overlay": "OVERLAY",
    "soft_light": "SOFTLIGHT", "hard_light": "HARDLIGHT", "darken": "DARKEN_ONLY", "lighten": "LIGHTEN_ONLY",
    "color_dodge": "DODGE", "color_burn": "BURN", "linear_dodge": "ADDITION", "linear_burn": "LINEAR_BURN",
    "difference": "DIFFERENCE", "exclusion": "EXCLUSION", "subtract": "SUBTRACT", "divide": "DIVIDE",
    "hue": "LCH_HUE", "saturation": "HSV_SATURATION", "color": "LCH_COLOR", "luminosity": "LUMINANCE",
    "pass_through": "PASS_THROUGH",
}
REVERSE_MODES = {v: k for k, v in BLEND_MODES.items()}
REVERSE_MODES.update({"HSV_HUE": "hue", "HSL_COLOR": "color", "HSV_VALUE": "luminosity", "LCH_LIGHTNESS": "luminosity"})


def gfile(path):
    return Gio.File.new_for_path(path)


def mode_of(name):
    return getattr(Gimp.LayerMode, BLEND_MODES.get(name, "NORMAL"))


def mode_name(mode):
    nick = mode.value_nick.upper().replace("-", "_") if hasattr(mode, "value_nick") else str(mode)
    for k in REVERSE_MODES:
        if nick == k or nick.endswith(k):
            return REVERSE_MODES[k]
    return "normal"


def load_layer(image, path, name=None):
    layer = Gimp.file_load_layer(RUN, image, gfile(path))
    if name:
        layer.set_name(name)
    return layer


def single_layer_image(path):
    image = Gimp.file_load(RUN, gfile(path))
    layer = image.get_layers()[0]
    if not layer.has_alpha():
        layer.add_alpha()
    return image, layer


def save_png(image, path):
    Gimp.file_save(RUN, image, gfile(path), None)


def export_drawable(drawable, path, width=None, height=None):
    """Export one drawable (layer or mask) to PNG at its own size."""
    w, h = drawable.get_width(), drawable.get_height()
    img = Gimp.Image.new(w, h, Gimp.ImageBaseType.RGB)
    copy = Gimp.Layer.new_from_drawable(drawable, img)
    img.insert_layer(copy, None, 0)
    copy.set_offsets(0, 0)
    copy.set_visible(True)
    copy.set_opacity(100.0)
    copy.set_mode(Gimp.LayerMode.NORMAL)
    if copy.get_mask() is not None:
        copy.remove_mask(Gimp.MaskApplyMode.DISCARD)
    save_png(img, path)
    img.delete()


def apply_mask_from_png(image, layer, mask_png):
    """Mask PNG is an RGBA image whose alpha holds the mask value."""
    tmp = load_layer(image, mask_png, "tmp-mask")
    image.insert_layer(tmp, None, 0)
    ox, oy = layer.get_offsets()[1:]
    tmp.set_offsets(ox, oy)
    image.select_item(Gimp.ChannelOps.REPLACE, tmp)
    mask = layer.create_mask(Gimp.AddMaskType.SELECTION)
    layer.add_mask(mask)
    Gimp.Selection.none(image)
    image.remove_layer(tmp)


# ----- operations -------------------------------------------------------------

def op_probe(job, args):
    avail = list(Gimp.DrawableFilter.operation_get_available())
    return {"version": Gimp.version(), "gegl_operations": sorted(a for a in avail if a.startswith("gegl:"))}


def op_filter(job, args):
    image, layer = single_layer_image(args["input"])
    f = Gimp.DrawableFilter.new(layer, args["operation"], "")
    config = f.get_config()
    applied = {}
    for key, value in (args.get("params") or {}).items():
        spec = config.find_property(key)
        if spec is None:
            raise ValueError("Unknown property '%s' for %s" % (key, args["operation"]))
        config.set_property(key, value)
        applied[key] = value
    f.update()
    layer.merge_filter(f)
    save_png(image, args["output"])
    image.delete()
    return {"applied": applied}


def op_filter_info(job, args):
    pspecs = Gimp.DrawableFilter.operation_get_pspecs(args["operation"])
    out = []
    for p in pspecs:
        item = {"name": p.name, "type": p.value_type.name, "blurb": p.get_blurb()}
        for attr in ("minimum", "maximum", "default_value"):
            if hasattr(p, attr):
                v = getattr(p, attr)
                if isinstance(v, (int, float, bool, str)):
                    item[attr] = v
        out.append(item)
    return {"operation": args["operation"], "properties": out}


def _paint_setup(args):
    Gimp.context_push()
    hardness = float(args.get("hardness", 0.5))
    choices = [(0.25, "2. Hardness 025"), (0.5, "2. Hardness 050"), (0.75, "2. Hardness 075"), (1.0, "2. Hardness 100")]
    name = min(choices, key=lambda c: abs(c[0] - hardness))[1]
    brush = Gimp.Brush.get_by_name(name)
    if brush is not None:
        Gimp.context_set_brush(brush)
    Gimp.context_set_brush_size(float(args.get("size", 30)))
    Gimp.context_set_opacity(float(args.get("opacity", 1.0)) * 100.0)
    Gimp.context_set_paint_mode(Gimp.LayerMode.NORMAL)
    return name


def _flat(stroke):
    out = []
    for p in stroke:
        out.extend([float(p[0]), float(p[1])])
    if len(out) == 2:  # GIMP needs at least one segment for a dab
        out.extend(out)
    return out


def op_clone(job, args):
    image, target = single_layer_image(args["target"])
    src = load_layer(image, args["source"], "source")
    image.insert_layer(src, None, 1)
    src.set_visible(False)
    brush = _paint_setup(args)
    try:
        sx, sy = args["source_point"]
        aligned = bool(args.get("aligned", True))
        offset = None
        for stroke in args["strokes"]:
            if offset is None or not aligned:
                offset = (sx - stroke[0][0], sy - stroke[0][1])
            first = stroke[0]
            Gimp.clone(target, src, Gimp.CloneType.IMAGE, first[0] + offset[0], first[1] + offset[1], _flat(stroke))
    finally:
        Gimp.context_pop()
    image.remove_layer(src)
    save_png(image, args["output"])
    image.delete()
    return {"brush": brush}


def op_heal(job, args):
    image, target = single_layer_image(args["target"])
    src = load_layer(image, args.get("source") or args["target"], "source")
    image.insert_layer(src, None, 1)
    src.set_visible(False)
    brush = _paint_setup(args)
    try:
        sx, sy = args["source_point"]
        first = args["strokes"][0][0]
        offset = (sx - first[0], sy - first[1])
        for stroke in args["strokes"]:
            Gimp.heal(target, src, stroke[0][0] + offset[0], stroke[0][1] + offset[1], _flat(stroke))
    finally:
        Gimp.context_pop()
    image.remove_layer(src)
    save_png(image, args["output"])
    image.delete()
    return {"brush": brush}


def _build_layers(image, parent, items, warnings):
    """items: top -> bottom, as GIMP stacks them."""
    position = 0
    for item in items:
        kind = item.get("kind")
        if kind == "group":
            layer = Gimp.GroupLayer.new(image, item["name"])
            image.insert_layer(layer, parent, position)
            _build_layers(image, layer, item.get("children", []), warnings)
        elif kind == "text" and item.get("text"):
            t = item["text"]
            font = Gimp.Font.get_by_name(t.get("font", "Sans-serif")) or Gimp.context_get_font()
            layer = Gimp.TextLayer.new(image, t["text"], font, float(t.get("size", 48)), Gimp.Unit.pixel())
            image.insert_layer(layer, parent, position)
            try:
                from gi.repository import Gegl
                c = t.get("color", "#ffffff")
                color = Gegl.Color.new(c[:7])
                layer.set_color(color)
            except Exception as exc:  # color API differences are non-fatal
                warnings.append("text color not applied for %s: %s" % (item["name"], exc))
            layer.set_offsets(int(item["x"]), int(item["y"]))
        else:
            layer = load_layer(image, item["png"], item["name"])
            image.insert_layer(layer, parent, position)
            layer.set_offsets(int(item["x"]), int(item["y"]))
        layer.set_name(item["name"])
        layer.set_visible(bool(item.get("visible", True)))
        layer.set_opacity(float(item.get("opacity", 1.0)) * 100.0)
        mode = item.get("blend_mode", "normal")
        if mode == "pass_through" and kind != "group":
            mode = "normal"
        try:
            layer.set_mode(mode_of(mode))
        except Exception as exc:
            warnings.append("blend mode %s not applied to %s: %s" % (mode, item["name"], exc))
        if item.get("clipped") and hasattr(layer, "set_composite_space"):
            warnings.append("clipping for '%s' is approximated (GIMP has no clipping masks)" % item["name"])
        if item.get("mask_png"):
            apply_mask_from_png(image, layer, item["mask_png"])
            if not item.get("mask_enabled", True):
                layer.set_apply_mask(False)
        position += 1


def op_export_xcf(job, args):
    spec = args["document"]
    image = Gimp.Image.new(int(spec["width"]), int(spec["height"]), Gimp.ImageBaseType.RGB)
    image.set_resolution(float(spec.get("resolution", 72)), float(spec.get("resolution", 72)))
    warnings = []
    _build_layers(image, None, spec["layers"], warnings)
    Gimp.file_save(RUN, image, gfile(args["output"]), None)
    n = len(image.get_layers())
    image.delete()
    return {"top_level_layers": n, "warnings": warnings}


def _dump(image, layers, out_dir, counter, parent_items):
    for layer in layers:  # GIMP order: top -> bottom
        counter[0] += 1
        idx = counter[0]
        ok, ox, oy = layer.get_offsets()
        item = {
            "name": layer.get_name(), "x": ox, "y": oy, "width": layer.get_width(), "height": layer.get_height(),
            "visible": layer.get_visible(), "opacity": layer.get_opacity() / 100.0,
            "blend_mode": mode_name(layer.get_mode()),
        }
        if layer.is_group():
            item["kind"] = "group"
            item["children"] = []
            _dump(image, layer.get_children(), out_dir, counter, item["children"])
        else:
            item["kind"] = "text" if layer.is_text_layer() else "raster"
            if item["kind"] == "text":
                try:
                    item["text"] = layer.get_text()
                    item["font_size"] = layer.get_font_size()[0]
                except Exception:
                    pass
            png = os.path.join(out_dir, "layer_%04d.png" % idx)
            export_drawable(layer, png)
            item["png"] = png
        mask = layer.get_mask()
        if mask is not None:
            mpng = os.path.join(out_dir, "mask_%04d.png" % idx)
            export_drawable(mask, mpng)
            item["mask_png"] = mpng
            item["mask_enabled"] = layer.get_apply_mask()
        parent_items.append(item)


def op_import(job, args):
    image = Gimp.file_load(RUN, gfile(args["input"]))
    out_dir = args["out_dir"]
    items = []
    _dump(image, image.get_layers(), out_dir, [0], items)
    res = image.get_resolution()
    result = {"width": image.get_width(), "height": image.get_height(), "layers": items,
              "resolution": res[1] if isinstance(res, tuple) and len(res) > 1 else 72.0}
    image.delete()
    return result


OPS = {"probe": op_probe, "filter": op_filter, "filter_info": op_filter_info, "clone": op_clone,
       "heal": op_heal, "export_xcf": op_export_xcf, "import": op_import}


def main():
    job_path = os.environ.get("IMAGE_STUDIO_JOB") or globals().get("IMAGE_STUDIO_JOB")
    with open(job_path, encoding="utf-8") as fh:
        job = json.load(fh)
    results = []
    for step in job["ops"]:
        name = step["op"]
        try:
            if name not in OPS:
                raise ValueError("operation not allowed: %s" % name)
            results.append({"op": name, "ok": True, "result": OPS[name](job, step.get("args", {}))})
        except Exception as exc:
            results.append({"op": name, "ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                            "traceback": traceback.format_exc(limit=4)})
            break
    out = os.path.join(os.path.dirname(job_path), "result.json")
    with open(out + ".tmp", "w", encoding="utf-8") as fh:
        json.dump({"results": results}, fh)
    os.replace(out + ".tmp", out)


main()
