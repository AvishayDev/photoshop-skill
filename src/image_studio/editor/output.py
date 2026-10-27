"""Previews and exports, with post-write verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, PngImagePlugin

from ..core.color import f_to_u8
from ..core.compositor import flatten_to_u8
from ..errors import StudioError, ValidationError
from ..research.licensing import assess_reuse, attribution_line
from ..security import resolve_write_path, slugify
from .base import EditorBase

FORMATS = {"png": "PNG", "jpeg": "JPEG", "jpg": "JPEG", "webp": "WEBP", "tiff": "TIFF"}


def checkerboard(h: int, w: int, cell: int = 12) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    board = (((yy // cell) + (xx // cell)) % 2).astype(np.float32)
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = (0.8 + 0.15 * board)[..., None]
    out[..., 3] = 1
    return out


class OutputOps(EditorBase):
    def render_preview(self, document_id: str, max_size: int = 1024, layer_id: str | None = None,
                       region: list[int] | None = None, background: str = "checkerboard",
                       hide_layers: list[str] | None = None) -> dict[str, Any]:
        """Render the composite (or one layer solo) to previews/ and return its path for visual inspection."""
        proj = self.project(document_id)
        doc = proj.doc
        if not 64 <= max_size <= 4096:
            raise ValidationError("max_size must be within 64..4096")
        if layer_id:
            canvas = self.compositor(proj).render(solo=layer_id)
        elif hide_layers:
            for lid in hide_layers:
                doc.layer(lid)
            canvas = self.compositor(proj).render(hidden=set(hide_layers))
        else:
            canvas = self.render_doc(proj)
        if region:
            x, y, w, h = [int(v) for v in region]
            if w < 1 or h < 1 or x < 0 or y < 0 or x + w > doc.width or y + h > doc.height:
                raise ValidationError("region must lie inside the canvas: [x, y, width, height]")
            canvas = canvas[y:y + h, x:x + w]
        if background == "checkerboard":
            from ..core.blending import composite
            canvas = composite(checkerboard(*canvas.shape[:2]), canvas)
            arr = f_to_u8(canvas)
        else:
            arr = flatten_to_u8(canvas, None if background == "transparent" else background)
        im = Image.fromarray(arr, "RGBA")
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        tag = f"r{doc.revision}" + (f"_{layer_id}" if layer_id else "") + ("_region" if region else "")
        path = proj.path("previews", f"preview_{tag}.png")
        im.save(path)
        return self.result(proj, preview_path=str(path), preview_size=list(im.size),
                           document_size=[doc.width, doc.height],
                           scale=round(im.size[0] / (region[2] if region else doc.width), 5),
                           hint="Open/view this file to inspect the result visually before continuing.")

    def export_image(self, document_id: str, path: str | None = None, format: str = "png", quality: int = 92,
                     width: int | None = None, height: int | None = None, background: str | None = None,
                     embed_credits: bool = True) -> dict[str, Any]:
        """Flatten (in memory only) and export. The editable project is untouched. Writes a .credits.json
        sidecar with source/licensing information for every composited asset."""
        proj = self.project(document_id)
        doc = proj.doc
        fmt_key = format.lower()
        if fmt_key not in FORMATS:
            raise ValidationError(f"format must be one of {sorted(FORMATS)}")
        pil_fmt = FORMATS[fmt_key]
        if not 1 <= quality <= 100:
            raise ValidationError("quality must be within 1..100")
        ext = "jpg" if pil_fmt == "JPEG" else fmt_key
        target = resolve_write_path(path or f"exports/{slugify(doc.name)}.{ext}", base=proj.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        canvas = self.render_doc(proj)
        if pil_fmt == "JPEG" and background is None:
            background = "#ffffff"
        arr = flatten_to_u8(canvas, background)
        im = Image.fromarray(arr, "RGBA")
        if width or height:
            w = width or int(round(doc.width * height / doc.height))
            h = height or int(round(doc.height * width / doc.width))
            if not (1 <= w <= 30000 and 1 <= h <= 30000):
                raise ValidationError("Export size out of range")
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        credits = self._credits(proj)
        save_kw: dict[str, Any] = {}
        if pil_fmt == "JPEG":
            im = im.convert("RGB")
            save_kw.update(quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
        elif pil_fmt == "WEBP":
            save_kw.update(quality=quality, method=6)
        elif pil_fmt == "PNG":
            meta = PngImagePlugin.PngInfo()
            meta.add_text("Software", "agent-image-studio")
            if embed_credits and credits["lines"]:
                meta.add_text("Credits", "\n".join(credits["lines"]))
            save_kw.update(pnginfo=meta, optimize=False, compress_level=6)
        tmp = target.with_name(target.name + ".tmp")
        im.save(tmp, format=pil_fmt, **save_kw)
        tmp.replace(target)
        verify = self.verify_export(target, pil_fmt, im.size)
        sidecar = target.with_name(target.name + ".credits.json")
        sidecar.write_text(json.dumps(credits, indent=1, ensure_ascii=False), encoding="utf-8")
        return self.result(proj, export_path=str(target), credits_path=str(sidecar), format=pil_fmt,
                           size=list(im.size), bytes=target.stat().st_size, verification=verify,
                           attribution_required=credits["attribution_required"],
                           credits=credits["lines"])

    def export_png(self, document_id: str, path: str | None = None, **kw) -> dict[str, Any]:
        return self.export_image(document_id, path, "png", **kw)

    def export_jpeg(self, document_id: str, path: str | None = None, quality: int = 92, **kw) -> dict[str, Any]:
        return self.export_image(document_id, path, "jpeg", quality=quality, **kw)

    def export_webp(self, document_id: str, path: str | None = None, quality: int = 90, **kw) -> dict[str, Any]:
        return self.export_image(document_id, path, "webp", quality=quality, **kw)

    @staticmethod
    def verify_export(path: Path, fmt: str, size: tuple[int, int]) -> dict[str, Any]:
        if not path.exists() or path.stat().st_size == 0:
            raise StudioError(f"Export failed: {path} was not written")
        with Image.open(path) as im:
            im.load()
            ok = im.format == fmt and im.size == tuple(size)
            out = {"exists": True, "opens": True, "format": im.format, "size": list(im.size), "matches": ok}
        if not ok:
            raise StudioError(f"Export verification failed: {out}")
        return out

    def _credits(self, proj) -> dict[str, Any]:
        doc = proj.doc
        used = {layer.source_asset for layer in doc.layers.values() if layer.source_asset and layer.visible}
        lines, items, required = [], [], False
        for aid in sorted(used):
            asset = doc.assets.get(aid)
            if not asset:
                continue
            pv = asset.provenance
            lic = pv.license
            verdict = assess_reuse(lic) if pv.origin == "web_reference" else None
            item = {"asset_id": aid, "kind": asset.kind, "origin": pv.origin, "source_url": pv.source_url,
                    "provider": pv.provider, "license": lic.model_dump() if lic else None, "assessment": verdict}
            if pv.origin == "generated":
                item["generator"] = pv.generator
            items.append(item)
            if verdict and verdict["attribution_required"]:
                required = True
                line = attribution_line(lic)
                if line:
                    lines.append(line)
        return {"document": doc.name, "assets": items, "attribution_required": required, "lines": lines}
