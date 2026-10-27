"""Document lifecycle: create/open/save, checkpoints, history, canvas geometry."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from ..core import geometry
from ..core.capabilities import backends
from ..core.document import Asset
from ..core.ids import new_id
from ..core.layer import BlendMode, FillProps, Layer, LayerKind, MaskRef
from ..core.project import Project
from ..core.provenance import Provenance
from ..core.render import render_fill
from ..errors import NotFoundError, UnsupportedOperationError, ValidationError
from ..security import resolve_read_path, resolve_write_path, slugify
from .base import EditorBase, load_rgba

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}


class DocumentOps(EditorBase):
    # ----- creation ------------------------------------------------------------------
    def create_project(self, name: str, width: int, height: int, background: str | None = "#ffffff",
                       resolution_dpi: float = 72.0) -> dict[str, Any]:
        proj = Project.create(name, width, height, workspace=self.workspace, resolution_dpi=resolution_dpi)
        self.register(proj)
        if background and background != "transparent":
            with proj.transaction("create_project", {"name": name, "width": width, "height": height,
                                                     "background": background}) as tx:
                props = FillProps(type="solid", color=background)
                layer = Layer(id=new_id("lyr"), name="Background", kind=LayerKind.fill, width=width, height=height,
                              fill=props)
                layer.pixels = proj.blobs.put(render_fill(props, width, height))
                tx.doc.insert(layer)
                tx.touch(layer.id)
        return self.result(proj, project_path=str(proj.root), document=proj.doc.summary())

    def list_projects(self) -> dict[str, Any]:
        out = []
        for mf in sorted(self.workspace.glob("*/project.json")):
            try:
                proj = Project.load(mf.parent)
                out.append({**proj.doc.summary(), "project_path": str(mf.parent)})
            except Exception as exc:  # report corrupt projects instead of hiding them
                out.append({"project_path": str(mf.parent), "error": str(exc)})
        return {"ok": True, "workspace": str(self.workspace), "projects": out}

    def _add_asset(self, proj: Project, tx, rgba: np.ndarray, src_path: Path | None, *, kind: str = "source",
                   role: str = "composited", provenance: Provenance | None = None, fmt: str | None = None) -> Asset:
        """Copy an original into assets/ (never modified) and register it."""
        aid = new_id("ast")
        if src_path is not None:
            data = src_path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            for a in tx.doc.assets.values():
                if a.sha256 == sha:
                    return a
            target = proj.path("assets", f"{aid}_{slugify(src_path.stem, 40)}{src_path.suffix.lower()}")
            shutil.copyfile(src_path, target)
        else:
            from PIL import Image
            target = proj.path("assets", f"{aid}.png")
            Image.fromarray(rgba, "RGBA").save(target)
            sha = hashlib.sha256(target.read_bytes()).hexdigest()
        asset = Asset(id=aid, kind=kind, role=role, path=str(target.relative_to(proj.root)), sha256=sha,
                      width=int(rgba.shape[1]), height=int(rgba.shape[0]), format=fmt,
                      provenance=provenance or Provenance(origin="local_file",
                                                          original_path=str(src_path) if src_path else None))
        tx.doc.assets[aid] = asset
        return asset

    def open_document(self, path: str, name: str | None = None) -> dict[str, Any]:
        """Open an image (new project with a protected original layer), a layered file, or a project folder."""
        p = resolve_read_path(path)
        if p.is_dir() or p.name == "project.json":
            root = p if p.is_dir() else p.parent
            proj = Project.load(root)
            self.register(proj)
            return self.result(proj, project_path=str(proj.root), document=proj.doc.summary(),
                               message="Opened existing project")
        suffix = p.suffix.lower()
        if suffix in (".ora", ".xcf", ".psd"):
            return self._open_layered(p, name)
        if suffix not in IMAGE_SUFFIXES:
            raise ValidationError(f"Unsupported file type '{suffix}'",
                                  hint=f"Supported: {sorted(IMAGE_SUFFIXES | {'.ora', '.xcf', '.psd'})}")
        rgba, info = load_rgba(p)
        h, w = rgba.shape[:2]
        proj = Project.create(name or p.stem, w, h, workspace=self.workspace)
        self.register(proj)
        with proj.transaction("open_document", {"path": str(p)}) as tx:
            asset = self._add_asset(proj, tx, rgba, p, fmt=info.get("format"))
            layer = Layer(id=new_id("lyr"), name="Original", width=w, height=h, locked_pixels=True,
                          source_asset=asset.id, metadata={"note": "Untouched original. Duplicate before editing."})
            layer.pixels = proj.blobs.put(rgba)
            tx.doc.insert(layer)
            tx.doc.metadata["source_image"] = {"path": str(p), **info}
            tx.touch(layer.id)
        return self.result(proj, tx, project_path=str(proj.root), document=proj.doc.summary(),
                           hint="The original is locked. Use duplicate_layer to create a working copy.")

    def _open_layered(self, p: Path, name: str | None) -> dict[str, Any]:
        suffix = p.suffix.lower()
        bs = backends()
        if suffix == ".ora":
            backend = bs["pillow"]
        else:
            backend = bs["gimp"]
            if not backend.status().available:
                raise UnsupportedOperationError(
                    f"Opening {suffix} files requires the GIMP 3 backend, which is unavailable.",
                    hint=backend.status().how_to_enable)
        work = self.workspace / ".import_tmp" / new_id("imp")
        try:
            imported = backend.import_native(p, work)
            proj = Project.create(name or p.stem, imported.width, imported.height, workspace=self.workspace,
                                  resolution_dpi=imported.resolution)
            self.register(proj)
            with proj.transaction("open_document", {"path": str(p), "format": suffix[1:]}, backend=backend.name) as tx:
                asset = self._add_asset(proj, tx, np.zeros((imported.height, imported.width, 4), np.uint8), p,
                                        fmt=suffix[1:].upper())
                tx.doc.metadata["source_document"] = {"path": str(p), "asset_id": asset.id}

                def add(items, parent):
                    for it in reversed(items):  # imported lists are top -> bottom
                        lid = new_id("lyr")
                        mode = it.blend_mode if it.blend_mode in BlendMode._value2member_map_ else "normal"
                        layer = Layer(id=lid, name=it.name, visible=it.visible, opacity=max(0, min(1, it.opacity)),
                                      blend_mode=BlendMode(mode), x=it.x, y=it.y)
                        if it.kind == "group":
                            layer.kind = LayerKind.group
                            layer.width, layer.height = imported.width, imported.height
                            layer.x = layer.y = 0
                            tx.doc.insert(layer, parent_id=parent)
                            add(it.children, lid)
                            continue
                        if layer.blend_mode == BlendMode.pass_through:
                            layer.blend_mode = BlendMode.normal
                        rgba, _ = load_rgba(it.png)
                        layer.pixels = proj.blobs.put(rgba)
                        layer.height, layer.width = rgba.shape[:2]
                        if it.text:
                            layer.metadata["native_text"] = it.text
                        if it.mask_png:
                            m, _ = load_rgba(it.mask_png)
                            gray = (m[..., :3].astype(np.float32).mean(-1)).astype(np.uint8)
                            if gray.shape == rgba.shape[:2]:
                                layer.mask = MaskRef(blob=proj.blobs.put(gray), enabled=it.mask_enabled)
                            else:
                                tx.warnings.append(f"Mask of '{it.name}' has a different size and was skipped")
                        tx.doc.insert(layer, parent_id=parent)
                        tx.touch(lid)

                add(imported.layers, None)
                tx.warnings.extend(imported.warnings)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return self.result(proj, tx, project_path=str(proj.root), document=proj.doc.summary())

    # ----- info ------------------------------------------------------------------------
    def get_document_info(self, document_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        doc = proj.doc
        return self.result(proj, document=doc.summary(), project_path=str(proj.root),
                           layers=[{**layer.summary(), "depth": d} for layer, d in doc.walk()],
                           checkpoints=[c.model_dump() for c in proj.manifest.checkpoints.values()],
                           assets=[a.model_dump(mode="json") for a in doc.assets.values()],
                           metadata=doc.metadata)

    def get_project_manifest(self, document_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        exports = sorted(str(p) for p in proj.path("exports").glob("*") if p.is_file())
        previews = sorted(str(p) for p in proj.path("previews").glob("*.png"))[-5:]
        refs = sorted(str(p) for p in proj.path("references").glob("*.json"))
        return self.result(proj, project_path=str(proj.root), manifest_path=str(proj.root / "project.json"),
                           document=proj.doc.summary(), exports=exports, recent_previews=previews,
                           reference_records=refs, plans=proj.manifest.plans,
                           history_length=len(proj.manifest.history),
                           assets=[{"id": a.id, "kind": a.kind, "role": a.role, "path": a.path,
                                    "license": a.provenance.license.model_dump() if a.provenance.license else None,
                                    "source_url": a.provenance.source_url} for a in proj.doc.assets.values()])

    def get_history(self, document_id: str, limit: int = 30) -> dict[str, Any]:
        proj = self.project(document_id)
        hist = proj.manifest.history[-max(1, min(limit, 500)):]
        return self.result(proj, history=[h.model_dump() for h in hist],
                           available_revisions=proj.available_revisions())

    # ----- checkpoints -----------------------------------------------------------------
    def create_checkpoint(self, document_id: str, name: str, note: str | None = None) -> dict[str, Any]:
        proj = self.project(document_id)
        cp = proj.create_checkpoint(name, note)
        return self.result(proj, checkpoint=cp.model_dump())

    def list_checkpoints(self, document_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        return self.result(proj, checkpoints=[c.model_dump() for c in proj.manifest.checkpoints.values()])

    def restore_checkpoint(self, document_id: str, checkpoint: str) -> dict[str, Any]:
        proj = self.project(document_id)
        cp = proj.resolve_checkpoint(checkpoint)
        tx = proj.restore_revision(cp.revision, op="restore_checkpoint",
                                   params={"checkpoint": cp.id, "name": cp.name, "revision": cp.revision})
        return self.result(proj, tx, restored_checkpoint=cp.model_dump())

    def undo(self, document_id: str, steps: int = 1) -> dict[str, Any]:
        proj = self.project(document_id)
        tx = proj.undo(steps)
        return self.result(proj, tx)

    def restore_revision(self, document_id: str, revision: int) -> dict[str, Any]:
        proj = self.project(document_id)
        tx = proj.restore_revision(revision)
        return self.result(proj, tx)

    # ----- canvas geometry -------------------------------------------------------------
    def crop_image(self, document_id: str, x: int, y: int, width: int, height: int) -> dict[str, Any]:
        """Crop the canvas. Layers keep their pixels (moved by the offset) so the crop is reversible."""
        proj = self.project(document_id)
        doc = proj.doc
        if width < 1 or height < 1:
            raise ValidationError("Crop width and height must be >= 1")
        if x < 0 or y < 0 or x + width > doc.width or y + height > doc.height:
            raise ValidationError(f"Crop rectangle ({x},{y},{width},{height}) exceeds the canvas "
                                  f"{doc.width}x{doc.height}")
        with proj.transaction("crop_image", {"x": x, "y": y, "width": width, "height": height}) as tx:
            self._shift_all(proj, tx, -x, -y)
            tx.doc.width, tx.doc.height = width, height
            if tx.doc.selection:
                sel = proj.blobs.get(tx.doc.selection)[y:y + height, x:x + width]
                tx.doc.selection = proj.blobs.put(np.ascontiguousarray(sel))
            tx.message = "Canvas cropped; layer content outside the canvas is preserved (non-destructive)."
        return self.result(proj, tx, document=proj.doc.summary())

    def resize_canvas(self, document_id: str, width: int, height: int, anchor: str = "center") -> dict[str, Any]:
        proj = self.project(document_id)
        doc = proj.doc
        anchors = {"top_left": (0, 0), "top": (0.5, 0), "top_right": (1, 0), "left": (0, 0.5), "center": (0.5, 0.5),
                   "right": (1, 0.5), "bottom_left": (0, 1), "bottom": (0.5, 1), "bottom_right": (1, 1)}
        if anchor not in anchors:
            raise ValidationError(f"anchor must be one of {list(anchors)}")
        if not (1 <= width <= 30000 and 1 <= height <= 30000):
            raise ValidationError("Canvas size must be within 1..30000")
        ax, ay = anchors[anchor]
        dx, dy = int(round((width - doc.width) * ax)), int(round((height - doc.height) * ay))
        with proj.transaction("resize_canvas", {"width": width, "height": height, "anchor": anchor}) as tx:
            self._shift_all(proj, tx, dx, dy)
            tx.doc.width, tx.doc.height = width, height
            tx.doc.selection = None
            for layer in tx.doc.layers.values():
                if layer.kind == LayerKind.fill and layer.fill and layer.x == dx and layer.y == dy:
                    layer.x = layer.y = 0
                    layer.width, layer.height = width, height
                    layer.pixels = proj.blobs.put(render_fill(layer.fill, width, height))
                    if layer.mask:
                        tx.warnings.append(f"Mask of fill layer '{layer.name}' was removed by the canvas resize")
                        layer.mask = None
        return self.result(proj, tx, document=proj.doc.summary())

    def _shift_all(self, proj, tx, dx: int, dy: int) -> None:
        for layer in tx.doc.layers.values():
            if layer.kind in (LayerKind.group, LayerKind.adjustment) and not layer.mask:
                layer.width, layer.height = tx.doc.width, tx.doc.height
                continue
            layer.x += dx
            layer.y += dy
            if layer.transform:
                m = geometry.translation(dx, dy) @ np.array(layer.transform)
                layer.transform = m.tolist()
            tx.touch(layer.id)

    def resize_image(self, document_id: str, width: int | None = None, height: int | None = None,
                     scale: float | None = None, interpolation: str = "lanczos") -> dict[str, Any]:
        """Scale the whole document (all layers, masks and selection)."""
        proj = self.project(document_id)
        doc = proj.doc
        if scale is not None:
            if not 0.01 <= scale <= 16:
                raise ValidationError("scale must be within 0.01..16")
            width, height = int(round(doc.width * scale)), int(round(doc.height * scale))
        elif width and not height:
            height = int(round(doc.height * width / doc.width))
        elif height and not width:
            width = int(round(doc.width * height / doc.height))
        if not width or not height or width < 1 or height < 1 or width > 30000 or height > 30000:
            raise ValidationError("Provide width and/or height (1..30000) or scale")
        sx, sy = width / doc.width, height / doc.height
        with proj.transaction("resize_image", {"width": width, "height": height, "interpolation": interpolation}) as tx:
            for layer in tx.doc.layers.values():
                if layer.kind in (LayerKind.group, LayerKind.adjustment):
                    layer.width, layer.height = width, height
                    if layer.mask:
                        m = proj.blobs.get(layer.mask.blob)
                        layer.mask.blob = proj.blobs.put(geometry.resize(m, width, height, "linear"))
                    continue
                if not layer.pixels:
                    continue
                if layer.text:
                    layer.text.size *= (sx + sy) / 2
                if layer.shape:
                    layer.shape.width = max(1, int(round(layer.shape.width * sx)))
                    layer.shape.height = max(1, int(round(layer.shape.height * sy)))
                    if layer.shape.points:
                        layer.shape.points = [[p[0] * sx, p[1] * sy] for p in layer.shape.points]
                nw, nh = max(1, int(round(layer.width * sx))), max(1, int(round(layer.height * sy)))
                arr = geometry.resize(self.pixels(proj, layer), nw, nh, interpolation)
                layer.pixels = proj.blobs.put(arr)
                if layer.mask:
                    m = proj.blobs.get(layer.mask.blob)
                    layer.mask.blob = proj.blobs.put(geometry.resize(m, nw, nh, "linear"))
                layer.x, layer.y = int(round(layer.x * sx)), int(round(layer.y * sy))
                layer.width, layer.height = nw, nh
                if layer.transform:
                    layer.transform = (np.diag([sx, sy, 1.0]) @ np.array(layer.transform)).tolist()
                tx.touch(layer.id)
            tx.doc.width, tx.doc.height = width, height
            if tx.doc.selection:
                sel = proj.blobs.get(tx.doc.selection)
                tx.doc.selection = proj.blobs.put(geometry.resize(sel, width, height, "linear"))
        return self.result(proj, tx, document=proj.doc.summary())

    # ----- saving ------------------------------------------------------------------------
    def save_document(self, document_id: str, format: str = "project", path: str | None = None) -> dict[str, Any]:
        """Persist the project and optionally write a layered native file (ora | xcf | psd)."""
        proj = self.project(document_id)
        manifest_path = proj.save()
        out: dict[str, Any] = {"project_path": str(proj.root), "manifest": str(manifest_path)}
        if format == "project":
            return self.result(proj, **out, message="Project saved (it is also saved after every operation).")
        fmt = format.lower()
        backend = {"ora": "pillow", "xcf": "gimp", "psd": "photoshop"}.get(fmt)
        if backend is None:
            raise ValidationError("format must be project, ora, xcf or psd")
        b = backends()[backend]
        st = b.status()
        if not st.available:
            raise UnsupportedOperationError(f"Saving .{fmt} requires the {backend} backend: {st.detail}",
                                            hint=(st.how_to_enable or "") + " The project itself is saved; "
                                            "OpenRaster (.ora) export is always available.")
        target = resolve_write_path(path or f"exports/{slugify(proj.doc.name)}.{fmt}", base=proj.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmpdir = proj.path("exports", f".native_{new_id('tmp')}")
        tmpdir.mkdir(parents=True)
        try:
            spec, warnings = self.native_spec(proj, tmpdir)
            res = b.export_native(spec, target, fmt)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        warnings = warnings + list(res.get("warnings", []))
        if not target.exists() or target.stat().st_size == 0:
            raise UnsupportedOperationError(f"{fmt} export did not produce a file")
        return self.result(proj, **out, native_file=str(target), format=fmt, backend=backend,
                           size_bytes=target.stat().st_size, warnings=warnings)

    def native_spec(self, proj: Project, tmpdir: Path) -> tuple[dict[str, Any], list[str]]:
        """Describe the document for native exporters: layers top -> bottom with PNG files."""
        from PIL import Image

        doc = proj.doc
        comp = self.compositor(proj)
        warnings: list[str] = []
        counter = [0]

        def png(arr, tag):
            counter[0] += 1
            p = tmpdir / f"{counter[0]:04d}_{tag}.png"
            Image.fromarray(arr, "RGBA" if arr.ndim == 3 else "L").save(p)
            return str(p)

        def item_for(layer: Layer) -> list[dict[str, Any]]:
            base = {"name": layer.name, "visible": layer.visible, "opacity": layer.opacity,
                    "blend_mode": layer.blend_mode.value, "x": layer.x, "y": layer.y, "clipped": layer.clipped}
            if layer.kind == LayerKind.group:
                return [{**base, "kind": "group", "children": [i for cid in reversed(layer.children)
                                                               for i in item_for(doc.layers[cid])]}]
            if layer.kind == LayerKind.adjustment:
                above = _next_above(doc, layer.id)
                after = comp.render(stop_at=above) if above else comp.render()
                warnings.append(f"Adjustment layer '{layer.name}' exported as a baked raster layer "
                                "(it contains the adjusted composite of everything below it)")
                return [{**base, "kind": "raster", "x": 0, "y": 0, "opacity": 1.0, "blend_mode": "normal",
                         "name": f"{layer.name} (baked adjustment)",
                         "png": png(np.clip(after * 255 + 0.5, 0, 255).astype(np.uint8), "adj")}]
            if not layer.pixels:
                return []
            item = {**base, "kind": "text" if layer.kind == LayerKind.text else "raster",
                    "png": png(proj.blobs.get(layer.pixels), "px")}
            if layer.text:
                item["text"] = layer.text.model_dump()
                item["kind"] = "raster"  # pixels are exact; native text would re-render with other fonts
                item["native_text_hint"] = layer.text.text
            if layer.mask:
                m = proj.blobs.get(layer.mask.blob)
                rgba_mask = np.zeros(m.shape + (4,), np.uint8)
                rgba_mask[..., 3] = m
                item["mask_png"] = png(rgba_mask, "mask")
                item["mask_gray_png"] = png(m, "maskgray")
                item["mask_enabled"] = layer.mask.enabled
                masked = proj.blobs.get(layer.pixels).copy()
                if layer.mask.enabled:
                    masked[..., 3] = (masked[..., 3].astype(np.float32) * m / 255 + 0.5).astype(np.uint8)
                item["png_masked"] = png(masked, "masked")
            out = [item]
            if layer.clipped:
                warnings.append(f"Clipping of '{layer.name}' is not represented in the native file")
            for eff in layer.effects:
                if not eff.enabled:
                    continue
                solo = layer.model_copy(update={"effects": [eff], "id": layer.id + "_fx", "opacity": 1.0,
                                                "parent_id": None, "clipped": False, "visible": True,
                                                "blend_mode": BlendMode.normal})
                tmpdoc = doc.model_copy(deep=True)
                tmpdoc.layers = {solo.id: solo}
                tmpdoc.root = [solo.id]
                full = self.compositor(proj, tmpdoc).render()
                content_only = self.compositor(proj, tmpdoc.model_copy(update={
                    "layers": {solo.id: solo.model_copy(update={"effects": []})}})).render()
                warnings.append(f"Effect '{eff.type}' on '{layer.name}' exported as a separate raster layer")
                pos = 0 if eff.type == "stroke" else len(out)
                out.insert(pos, {"name": f"{layer.name} · {eff.type}", "kind": "raster", "visible": layer.visible,
                                 "opacity": layer.opacity, "blend_mode": "normal", "x": 0, "y": 0,
                                 "png": png(_effect_only(full, content_only), "fx")})
            return out

        layers = [i for lid in reversed(doc.root) for i in item_for(doc.layers[lid])]
        merged = png(np.clip(self.render_doc(proj) * 255 + 0.5, 0, 255).astype(np.uint8), "merged")
        spec = {"name": doc.name, "width": doc.width, "height": doc.height, "resolution": doc.resolution_dpi,
                "layers": layers, "merged_png": merged}
        return spec, warnings


def _effect_only(full: np.ndarray, content: np.ndarray) -> np.ndarray:
    """Pixels contributed by an effect: where the effect render differs from the plain content."""
    diff_alpha = np.clip(full[..., 3] - content[..., 3], 0, 1)
    out = np.zeros(full.shape, np.float32)
    out[..., :3] = full[..., :3]
    out[..., 3] = diff_alpha
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)


def _next_above(doc, layer_id: str) -> str | None:
    layer = doc.layer(layer_id)
    sib = doc.siblings(layer)
    i = sib.index(layer_id)
    if i + 1 < len(sib):
        return sib[i + 1]
    if layer.parent_id:
        return _next_above(doc, layer.parent_id)
    return None


__all__ = ["DocumentOps", "NotFoundError"]
