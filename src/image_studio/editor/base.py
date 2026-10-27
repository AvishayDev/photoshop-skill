"""Shared editor plumbing: project registry, pixel helpers, result formatting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageCms, ImageOps

from ..config import get_settings
from ..core.capabilities import backends
from ..core.compositor import Compositor
from ..core.layer import Layer, LayerKind
from ..core.project import Project, TxContext
from ..errors import NotFoundError, UnsupportedOperationError, ValidationError
from ..security import open_image_safely


def load_rgba(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Open an image file as sRGB RGBA uint8, honoring EXIF orientation and ICC profiles."""
    im = open_image_safely(path)
    info: dict[str, Any] = {"format": im.format, "mode": im.mode, "original_size": list(im.size)}
    im = ImageOps.exif_transpose(im)
    icc = im.info.get("icc_profile")
    if icc and im.mode in ("RGB", "RGBA", "CMYK"):
        try:
            import io
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.createProfile("sRGB")
            mode = "RGBA" if im.mode == "RGBA" else "RGB"
            im = ImageCms.profileToProfile(im, src, dst, outputMode=mode)
            info["converted_from_icc"] = True
        except Exception:
            info["icc_conversion_failed"] = True
    if im.mode in ("I;16", "I", "F"):
        info["warning"] = "High bit-depth image reduced to 8 bits per channel"
        arr = np.asarray(im).astype(np.float32)
        arr = (arr / max(arr.max(), 1) * 255).astype(np.uint8)
        im = Image.fromarray(arr, "L")
    rgba = np.asarray(im.convert("RGBA")).copy()
    return rgba, info


class EditorBase:
    def __init__(self, workspace: Path | None = None):
        self.workspace = workspace or get_settings().workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._projects: dict[str, Project] = {}
        self._render_cache: dict[str, tuple[int, np.ndarray]] = {}

    # ----- registry --------------------------------------------------------------
    def _index_path(self) -> Path:
        return self.workspace / ".index.json"

    def _write_index(self) -> None:
        idx = {}
        for p in self.workspace.glob("*/project.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                idx[data["document"]["id"]] = p.parent.name
            except Exception:
                continue
        self._index_path().write_text(json.dumps(idx, indent=1), encoding="utf-8")

    def register(self, project: Project) -> Project:
        self._projects[project.id] = project
        self._write_index()
        return project

    def project(self, document_id: str) -> Project:
        if document_id in self._projects:
            return self._projects[document_id]
        idx = {}
        if self._index_path().exists():
            try:
                idx = json.loads(self._index_path().read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                idx = {}
        folder = idx.get(document_id)
        if folder is None or not (self.workspace / folder / "project.json").exists():
            self._write_index()
            idx = json.loads(self._index_path().read_text(encoding="utf-8"))
            folder = idx.get(document_id)
        if folder is None:
            raise NotFoundError(f"No document '{document_id}' in workspace {self.workspace}",
                                hint="Call list_projects, or open_document with a project folder path.")
        proj = Project.load(self.workspace / folder)
        self._projects[proj.id] = proj
        return proj

    # ----- pixel helpers -----------------------------------------------------------
    def compositor(self, proj: Project, doc=None) -> Compositor:
        return Compositor(doc or proj.doc, proj.blobs)

    def render_doc(self, proj: Project, doc=None, **kw) -> np.ndarray:
        doc = doc or proj.doc
        if not kw and doc is proj.doc:
            cached = self._render_cache.get(proj.id)
            if cached and cached[0] == doc.revision:
                return cached[1].copy()
            out = self.compositor(proj, doc).render()
            self._render_cache[proj.id] = (doc.revision, out)
            return out.copy()
        return self.compositor(proj, doc).render(**kw)

    def pixels(self, proj: Project, layer: Layer) -> np.ndarray:
        if not layer.pixels:
            raise ValidationError(f"Layer '{layer.name}' ({layer.id}) has no pixel content",
                                  hint="Groups and adjustment layers have no pixels; choose a raster layer.")
        return proj.blobs.get(layer.pixels)

    def mask(self, proj: Project, layer: Layer) -> np.ndarray | None:
        return proj.blobs.get(layer.mask.blob) if layer.mask else None

    def check_editable(self, layer: Layer, *, pixels: bool = True) -> None:
        if pixels and layer.locked_pixels:
            raise ValidationError(
                f"Layer '{layer.name}' has locked pixels (originals are protected).",
                hint="duplicate_layer to get a working copy, or set_layer_properties(locked_pixels=false).")
        if pixels and layer.kind in (LayerKind.group, LayerKind.adjustment):
            raise ValidationError(f"Layer '{layer.name}' is a {layer.kind.value} layer and has no pixels to edit")

    def set_pixels(self, proj: Project, tx: TxContext, layer: Layer, arr: np.ndarray, *,
                   x: int | None = None, y: int | None = None, keep_smart: bool = False) -> None:
        if arr.ndim != 3 or arr.shape[2] != 4 or arr.dtype != np.uint8:
            raise ValidationError("internal: layer pixels must be HxWx4 uint8")
        layer.pixels = proj.blobs.put(arr)
        layer.height, layer.width = arr.shape[:2]
        if x is not None:
            layer.x = int(x)
        if y is not None:
            layer.y = int(y)
        if not keep_smart:
            if layer.base_blob or layer.transform:
                tx.warnings.append(f"Layer '{layer.name}' smart transform was baked into pixels by this edit")
            layer.base_blob = None
            layer.transform = None
            if layer.kind in (LayerKind.text, LayerKind.shape, LayerKind.fill):
                tx.warnings.append(f"Layer '{layer.name}' was rasterized ({layer.kind.value} properties are no "
                                   "longer editable)")
                layer.kind = LayerKind.raster
        tx.touch(layer.id)

    def doc_mask_to_layer(self, mask_doc: np.ndarray, layer: Layer) -> np.ndarray:
        """Crop/pad a document-sized mask to a layer's pixel bounds."""
        H, W = mask_doc.shape
        out = np.zeros((layer.height, layer.width), mask_doc.dtype)
        x0, y0 = max(0, layer.x), max(0, layer.y)
        x1, y1 = min(W, layer.x + layer.width), min(H, layer.y + layer.height)
        if x1 > x0 and y1 > y0:
            out[y0 - layer.y:y1 - layer.y, x0 - layer.x:x1 - layer.x] = mask_doc[y0:y1, x0:x1]
        return out

    def selection_doc(self, proj: Project, doc=None, required: bool = True) -> np.ndarray | None:
        doc = doc or proj.doc
        if not doc.selection:
            if required:
                raise ValidationError("There is no active selection", hint="Call create_selection or select_by_color first.")
            return None
        return proj.blobs.get(doc.selection).astype(np.float32) / 255

    def backend_for(self, op_cap: str, requested: str | None):
        bs = backends()
        name = (requested or "auto").lower()
        if name == "auto":
            pref = get_settings().backend
            if pref in bs and pref != "auto" and bs[pref].supports(op_cap):
                return bs[pref]
            return bs["pillow"]
        if name not in bs:
            raise ValidationError(f"Unknown backend '{requested}'", details={"available": list(bs)})
        b = bs[name]
        if op_cap not in b.capabilities():
            raise UnsupportedOperationError(f"Backend '{name}' does not support {op_cap}")
        st = b.status()
        if not st.available:
            raise UnsupportedOperationError(f"Backend '{name}' is not available: {st.detail}", hint=st.how_to_enable)
        return b

    @staticmethod
    def clip_stack_top(doc, base_id: str) -> str:
        """Topmost layer of the clipping stack sitting on ``base_id`` (or the base itself), so a new
        clipped layer is applied after the existing ones, in call order."""
        base = doc.layer(base_id)
        stack = doc.siblings(base)
        i = stack.index(base_id)
        while i + 1 < len(stack) and doc.layers[stack[i + 1]].clipped:
            i += 1
        return stack[i]

    # ----- results ---------------------------------------------------------------------
    @staticmethod
    def result(proj: Project, tx: TxContext | None = None, **extra) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": True, "document_id": proj.id, "revision": proj.doc.revision}
        if tx is not None:
            out["affected_layers"] = tx.affected
            if tx.warnings:
                out["warnings"] = tx.warnings
            if tx.backend:
                out["backend"] = tx.backend
            if tx.message:
                out["message"] = tx.message
            out.update(tx.result)
        out.update(extra)
        return out
