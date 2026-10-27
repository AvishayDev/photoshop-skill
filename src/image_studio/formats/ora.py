"""OpenRaster (.ora) reader/writer.

OpenRaster is a free, documented layered format (https://www.openraster.org/)
read by GIMP, Krita and MyPaint. It supports layer stacks, groups, offsets,
opacity, visibility and SVG compositing operators, but not layer masks: masks
are baked into layer alpha on export (reported as a warning). The project's
own ``project.json`` remains the lossless, fully editable master.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..errors import ValidationError
from ..security import open_image_safely

TO_ORA = {
    "normal": "svg:src-over", "multiply": "svg:multiply", "screen": "svg:screen", "overlay": "svg:overlay",
    "darken": "svg:darken", "lighten": "svg:lighten", "color_dodge": "svg:color-dodge", "color_burn": "svg:color-burn",
    "hard_light": "svg:hard-light", "soft_light": "svg:soft-light", "difference": "svg:difference",
    "exclusion": "svg:exclusion", "hue": "svg:hue", "saturation": "svg:saturation", "color": "svg:color",
    "luminosity": "svg:luminosity", "linear_dodge": "svg:plus",
}
FROM_ORA = {v: k for k, v in TO_ORA.items()}
MAX_MEMBER_BYTES = 512 * 1024 * 1024


def write_ora(spec: dict[str, Any], out_path: Path) -> dict[str, Any]:
    warnings: list[str] = []
    root = ET.Element("image", {"version": "0.0.6", "w": str(spec["width"]), "h": str(spec["height"]),
                                "xres": str(int(spec.get("resolution", 72))), "yres": str(int(spec.get("resolution", 72)))})
    top = ET.SubElement(root, "stack")
    files: list[tuple[str, bytes]] = []
    counter = [0]

    def add(parent: ET.Element, items: list[dict[str, Any]]):
        for item in items:  # top -> bottom, as ORA stacks are ordered
            mode = item.get("blend_mode", "normal")
            attrs = {"name": item["name"], "opacity": f"{float(item.get('opacity', 1)):.4f}",
                     "visibility": "visible" if item.get("visible", True) else "hidden"}
            if item.get("kind") == "group":
                attrs["isolation"] = "auto" if mode == "pass_through" else "isolate"
                if mode not in ("pass_through", "normal"):
                    attrs["composite-op"] = TO_ORA.get(mode, "svg:src-over")
                el = ET.SubElement(parent, "stack", attrs)
                add(el, item.get("children", []))
                continue
            counter[0] += 1
            src = f"data/layer{counter[0]:04d}.png"
            img = np.asarray(Image.open(item["png"]).convert("RGBA")).copy()
            if item.get("mask_gray_png") and item.get("mask_enabled", True):
                m = np.asarray(Image.open(item["mask_gray_png"]).convert("L")).astype(np.float32) / 255
                img[..., 3] = (img[..., 3].astype(np.float32) * m + 0.5).astype(np.uint8)
                warnings.append(f"Mask of '{item['name']}' baked into alpha (OpenRaster has no layer masks)")
            if mode not in TO_ORA:
                warnings.append(f"Blend mode '{mode}' of '{item['name']}' is not in OpenRaster; exported as normal")
            buf = io.BytesIO()
            Image.fromarray(img, "RGBA").save(buf, "PNG")
            files.append((src, buf.getvalue()))
            attrs.update({"src": src, "x": str(int(item["x"])), "y": str(int(item["y"])),
                          "composite-op": TO_ORA.get(mode, "svg:src-over")})
            ET.SubElement(parent, "layer", attrs)

    add(top, spec["layers"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".ora.tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "image/openraster", compress_type=zipfile.ZIP_STORED)
        z.writestr("stack.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True),
                   compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files:
            z.writestr(name, data, compress_type=zipfile.ZIP_STORED)
        merged = spec.get("merged_png")
        if merged:
            data = Path(merged).read_bytes()
            z.writestr("mergedimage.png", data, compress_type=zipfile.ZIP_STORED)
            im = Image.open(io.BytesIO(data))
            im.thumbnail((256, 256))
            tb = io.BytesIO()
            im.save(tb, "PNG")
            z.writestr("Thumbnails/thumbnail.png", tb.getvalue(), compress_type=zipfile.ZIP_STORED)
    tmp.replace(out_path)
    return {"layers_written": counter[0], "warnings": warnings}


def read_ora(path: Path, work_dir: Path):
    from ..backends.base import ImportedDocument, ImportedLayer

    work_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "stack.xml" not in names:
            raise ValidationError("Not an OpenRaster file: stack.xml missing")
        for info in z.infolist():
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValidationError(f"OpenRaster member {info.filename} is too large")
        root = ET.fromstring(z.read("stack.xml"))
        counter = [0]

        def parse(stack: ET.Element) -> list[ImportedLayer]:
            out = []
            for el in stack:
                op = el.get("composite-op", "svg:src-over")
                common = dict(name=el.get("name", "Layer"), visible=el.get("visibility", "visible") != "hidden",
                              opacity=float(el.get("opacity", 1.0)))
                if el.tag == "stack":
                    mode = "pass_through" if el.get("isolation", "auto") == "auto" else FROM_ORA.get(op, "normal")
                    out.append(ImportedLayer(kind="group", x=0, y=0, png=None, blend_mode=mode,
                                             children=parse(el), **common))
                elif el.tag == "layer":
                    src = el.get("src", "")
                    if src not in names:  # never follow paths that aren't members of this archive
                        continue
                    counter[0] += 1
                    target = work_dir / f"ora_layer_{counter[0]:04d}.png"
                    target.write_bytes(z.read(src))
                    open_image_safely(target)
                    out.append(ImportedLayer(kind="raster", x=int(float(el.get("x", 0))), y=int(float(el.get("y", 0))),
                                             png=target, blend_mode=FROM_ORA.get(op, "normal"), **common))
            return out

        stack = root.find("stack")
        layers = parse(stack) if stack is not None else []
    return ImportedDocument(width=int(root.get("w")), height=int(root.get("h")), layers=layers,
                            resolution=float(root.get("xres", 72)))
