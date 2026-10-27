"""Layer management: create, import, duplicate, reorder, properties, groups, merging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..core import geometry
from ..core.blending import composite
from ..core.color import f_to_u8, u8_to_f
from ..core.compositor import Compositor
from ..core.ids import new_id
from ..core.layer import BlendMode, Layer, LayerKind
from ..core.provenance import LicenseInfo, Provenance
from ..errors import NotFoundError, ValidationError
from ..research.licensing import assess_reuse, attribution_line
from ..security import resolve_read_path, safe_child
from .base import EditorBase, load_rgba


def _opaque_bbox(rgba: np.ndarray) -> list[int] | None:
    ys, xs = np.nonzero(rgba[..., 3] > 8)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() + 1 - xs.min()), int(ys.max() + 1 - ys.min())]


class LayerOps(EditorBase):
    # ----- inspection ------------------------------------------------------------------
    def list_layers(self, document_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        return self.result(proj, order="top_to_bottom",
                           layers=[{**layer.summary(), "depth": d} for layer, d in proj.doc.walk()])

    def get_layer_info(self, document_id: str, layer_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        layer = proj.doc.layer(layer_id)
        info = layer.summary()
        info["metadata"] = layer.metadata
        if layer.shape:
            info["shape"] = layer.shape.model_dump()
        if layer.fill:
            info["fill"] = layer.fill.model_dump()
        if layer.text:
            info["text_props"] = layer.text.model_dump()
        if layer.pixels:
            arr = proj.blobs.get(layer.pixels)
            bbox = _opaque_bbox(arr)
            info["opaque_bounds_local"] = bbox
            if bbox:
                info["opaque_bounds_document"] = [bbox[0] + layer.x, bbox[1] + layer.y, bbox[2], bbox[3]]
                vis = arr[arr[..., 3] > 8][:, :3]
                info["mean_color"] = [int(c) for c in vis.mean(0)]
            info["coverage"] = round(float((arr[..., 3] > 8).mean()), 4)
        if layer.source_asset and layer.source_asset in proj.doc.assets:
            info["asset"] = proj.doc.assets[layer.source_asset].model_dump(mode="json")
        return self.result(proj, layer=info)

    # ----- creation ----------------------------------------------------------------------
    def _place(self, tx, layer: Layer, above: str | None, parent_id: str | None, position: str | None) -> None:
        if above:
            ref = tx.doc.layer(above)
            tx.doc.insert(layer, parent_id=ref.parent_id, above=above)
        elif position == "bottom":
            tx.doc.insert(layer, parent_id=parent_id, index=0)
        else:
            tx.doc.insert(layer, parent_id=parent_id)

    def create_layer(self, document_id: str, name: str = "Layer", fill_color: str | None = None,
                     above: str | None = None, parent_id: str | None = None, position: str | None = None,
                     opacity: float = 1.0, blend_mode: str = "normal") -> dict[str, Any]:
        """Create an empty (transparent) or solid-filled canvas-sized raster layer."""
        proj = self.project(document_id)
        from ..core.color import parse_color
        with proj.transaction("create_layer", {"name": name, "fill_color": fill_color}) as tx:
            W, H = tx.doc.width, tx.doc.height
            arr = np.zeros((H, W, 4), np.uint8)
            if fill_color:
                arr[...] = parse_color(fill_color)
            layer = Layer(id=new_id("lyr"), name=name, width=W, height=H, opacity=opacity,
                          blend_mode=BlendMode(blend_mode))
            layer.pixels = proj.blobs.put(arr)
            self._place(tx, layer, above, parent_id, position)
            tx.touch(layer.id)
            tx.result["layer_id"] = layer.id
        return self.result(proj, tx)

    def import_image_as_layer(self, document_id: str, path: str | None = None, reference_id: str | None = None,
                              name: str | None = None, x: int | None = None, y: int | None = None,
                              fit: str = "none", scale: float | None = None, above: str | None = None,
                              parent_id: str | None = None, license_acknowledged: bool = False,
                              locked_original: bool = False) -> dict[str, Any]:
        """Import a local image or a researched reference as a new layer (original copied to assets/)."""
        proj = self.project(document_id)
        if bool(path) == bool(reference_id):
            raise ValidationError("Provide exactly one of path or reference_id")
        warnings: list[str] = []
        provenance = None
        kind = "source"
        if reference_id:
            rec_path = safe_child(proj.root / "references", f"{reference_id}.json")
            if not rec_path.exists():
                raise NotFoundError(f"No downloaded reference '{reference_id}' in this project",
                                    hint="Use fetch_reference first (with size='full' for compositing).")
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            lic = LicenseInfo(**rec["license"]) if rec.get("license") else None
            verdict = assess_reuse(lic)
            if not verdict["composite_allowed"] and not license_acknowledged:
                raise ValidationError(
                    f"Reference '{reference_id}' may not be composited: {verdict['notes']}",
                    hint="Use it only for visual study, choose a CC0/PD/CC BY(-SA) image, or pass "
                         "license_acknowledged=true if you have verified rights yourself.",
                    details={"license": rec.get("license"), "assessment": verdict})
            if verdict["attribution_required"]:
                warnings.append("Attribution required: " + (attribution_line(lic, rec.get("title")) or "see license"))
            if verdict["share_alike"]:
                warnings.append("ShareAlike: the final image must be released under the same license.")
            file_path = safe_child(proj.root, *Path(rec["local_path"]).parts)
            provenance = Provenance(origin="web_reference", source_url=rec.get("source_page"),
                                    provider=rec.get("provider"), provider_id=rec.get("provider_id"),
                                    retrieved_at=rec.get("retrieved_at"), license=lic)
            kind = "reference"
            name = name or rec.get("title", "Reference")[:60]
        else:
            file_path = resolve_read_path(path)
        rgba, info = load_rgba(file_path)
        with proj.transaction("import_image_as_layer", {"path": path, "reference_id": reference_id, "fit": fit,
                                                        "scale": scale}) as tx:
            asset = self._add_asset(proj, tx, rgba, file_path, kind=kind, provenance=provenance,
                                    fmt=info.get("format"))
            W, H = tx.doc.width, tx.doc.height
            h, w = rgba.shape[:2]
            factor = 1.0
            if fit == "contain":
                factor = min(W / w, H / h)
            elif fit == "cover":
                factor = max(W / w, H / h)
            elif fit == "width":
                factor = W / w
            elif fit == "height":
                factor = H / h
            elif fit != "none":
                raise ValidationError("fit must be none, contain, cover, width or height")
            if scale is not None:
                if not 0.001 <= scale <= 50:
                    raise ValidationError("scale must be within 0.001..50")
                factor *= scale
            layer = Layer(id=new_id("lyr"), name=name or file_path.stem, source_asset=asset.id,
                          locked_pixels=locked_original)
            if abs(factor - 1.0) > 1e-6:
                # smart layer: keep the full-resolution original and re-render through the transform
                layer.base_blob = proj.blobs.put(rgba)
                nw, nh = max(1, int(round(w * factor))), max(1, int(round(h * factor)))
                px = int(round((W - nw) / 2)) if x is None else int(x)
                py = int(round((H - nh) / 2)) if y is None else int(y)
                m = geometry.translation(px, py) @ np.diag([nw / w, nh / h, 1.0])
                arr, ox, oy = geometry.warp(rgba, m, "lanczos" if factor > 1 else "area")
                layer.transform = m.tolist()
                layer.pixels = proj.blobs.put(arr)
                layer.x, layer.y = ox, oy
                layer.height, layer.width = arr.shape[:2]
            else:
                layer.pixels = proj.blobs.put(rgba)
                layer.width, layer.height = w, h
                layer.x = int(round((W - w) / 2)) if x is None else int(x)
                layer.y = int(round((H - h) / 2)) if y is None else int(y)
            self._place(tx, layer, above, parent_id, None)
            tx.touch(layer.id)
            tx.warnings.extend(warnings)
            tx.result.update(layer_id=layer.id, asset_id=asset.id, scale_applied=round(factor, 5))
        return self.result(proj, tx)

    def duplicate_layer(self, document_id: str, layer_id: str, name: str | None = None,
                        unlock: bool = True) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("duplicate_layer", {"layer_id": layer_id}) as tx:
            src = tx.doc.layer(layer_id)

            def clone(layer: Layer, parent: str | None, above: str | None, top: bool) -> str:
                data = layer.model_dump()
                data.update(id=new_id("lyr"), children=[], parent_id=None,
                            name=(name or f"{layer.name} copy") if top else layer.name)
                if top and unlock:
                    data["locked_pixels"] = False
                copy = Layer.model_validate(data)
                if above:
                    tx.doc.insert(copy, parent_id=parent, above=above)
                else:
                    tx.doc.insert(copy, parent_id=parent)
                for cid in layer.children:
                    clone(tx.doc.layers[cid], copy.id, None, False)
                tx.touch(copy.id)
                return copy.id

            new = clone(src, src.parent_id, src.id, True)
            tx.result["layer_id"] = new
        return self.result(proj, tx)

    def delete_layer(self, document_id: str, layer_id: str) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("delete_layer", {"layer_id": layer_id}) as tx:
            removed = tx.doc.remove(layer_id)
            tx.result["removed_layers"] = removed
            tx.message = "Deleted (recoverable with undo or restore_checkpoint)"
        return self.result(proj, tx)

    def rename_layer(self, document_id: str, layer_id: str, name: str) -> dict[str, Any]:
        if not name.strip():
            raise ValidationError("Layer name must not be empty")
        return self.set_layer_properties(document_id, layer_id, name=name)

    def set_layer_properties(self, document_id: str, layer_id: str, *, name: str | None = None,
                             visible: bool | None = None, opacity: float | None = None,
                             blend_mode: str | None = None, clipped: bool | None = None,
                             locked_pixels: bool | None = None, x: int | None = None,
                             y: int | None = None) -> dict[str, Any]:
        proj = self.project(document_id)
        params = {k: v for k, v in dict(name=name, visible=visible, opacity=opacity, blend_mode=blend_mode,
                                        clipped=clipped, locked_pixels=locked_pixels, x=x, y=y).items()
                  if v is not None}
        if not params:
            raise ValidationError("No properties given")
        with proj.transaction("set_layer_properties", {"layer_id": layer_id, **params}) as tx:
            layer = tx.doc.layer(layer_id)
            if opacity is not None and not 0 <= opacity <= 1:
                raise ValidationError("opacity must be within 0..1")
            if blend_mode is not None:
                try:
                    mode = BlendMode(blend_mode)
                except ValueError:
                    raise ValidationError(f"Unknown blend mode '{blend_mode}'",
                                          details={"available": [m.value for m in BlendMode]}) from None
                if mode == BlendMode.pass_through and layer.kind != LayerKind.group:
                    raise ValidationError("pass_through is only valid for groups")
                layer.blend_mode = mode
            if name is not None:
                layer.name = name
            if visible is not None:
                layer.visible = visible
            if opacity is not None:
                layer.opacity = float(opacity)
            if clipped is not None:
                layer.clipped = clipped
            if locked_pixels is not None:
                layer.locked_pixels = locked_pixels
            if x is not None or y is not None:
                dx = (x - layer.x) if x is not None else 0
                dy = (y - layer.y) if y is not None else 0
                self._translate(tx, layer, dx, dy)
            tx.touch(layer_id)
            tx.result["layer"] = layer.summary()
        return self.result(proj, tx)

    def set_layer_visibility(self, document_id: str, layer_id: str, visible: bool) -> dict[str, Any]:
        return self.set_layer_properties(document_id, layer_id, visible=visible)

    def set_layer_opacity(self, document_id: str, layer_id: str, opacity: float) -> dict[str, Any]:
        return self.set_layer_properties(document_id, layer_id, opacity=opacity)

    def set_blend_mode(self, document_id: str, layer_id: str, blend_mode: str) -> dict[str, Any]:
        return self.set_layer_properties(document_id, layer_id, blend_mode=blend_mode)

    def _translate(self, tx, layer: Layer, dx: int, dy: int) -> None:
        layer.x += dx
        layer.y += dy
        if layer.transform:
            layer.transform = (geometry.translation(dx, dy) @ np.array(layer.transform)).tolist()
        if layer.kind == LayerKind.group:
            for cid in tx.doc.descendants(layer.id):
                child = tx.doc.layers[cid]
                child.x += dx
                child.y += dy
                if child.transform:
                    child.transform = (geometry.translation(dx, dy) @ np.array(child.transform)).tolist()
                tx.touch(cid)

    # ----- ordering & groups -------------------------------------------------------------
    def move_layer(self, document_id: str, layer_id: str, position: str = "up", reference_layer_id: str | None = None,
                   group_id: str | None = None) -> dict[str, Any]:
        """Reorder a layer: position = up | down | top | bottom | above | below | into_group | out_of_group."""
        proj = self.project(document_id)
        with proj.transaction("move_layer", {"layer_id": layer_id, "position": position,
                                             "reference_layer_id": reference_layer_id, "group_id": group_id}) as tx:
            doc = tx.doc
            layer = doc.layer(layer_id)
            stack = doc.siblings(layer)
            i = stack.index(layer_id)
            if position in ("up", "down"):
                j = min(len(stack) - 1, i + 1) if position == "up" else max(0, i - 1)
                stack.insert(j, stack.pop(i))
            elif position in ("top", "bottom"):
                stack.pop(i)
                stack.insert(len(stack) if position == "top" else 0, layer_id)
            elif position in ("above", "below"):
                if not reference_layer_id:
                    raise ValidationError("reference_layer_id is required for above/below")
                ref = doc.layer(reference_layer_id)
                if reference_layer_id == layer_id or reference_layer_id in doc.descendants(layer_id):
                    raise ValidationError("Cannot move a layer relative to itself or its own children")
                doc.detach(layer_id)
                layer.parent_id = ref.parent_id
                target = doc.siblings(ref)
                k = target.index(reference_layer_id)
                target.insert(k + 1 if position == "above" else k, layer_id)
            elif position == "into_group":
                group = doc.layer(group_id or "")
                if group.kind != LayerKind.group:
                    raise ValidationError("group_id must be a group layer")
                if group_id == layer_id or group_id in doc.descendants(layer_id):
                    raise ValidationError("Cannot move a group into itself")
                doc.detach(layer_id)
                layer.parent_id = group.id
                group.children.append(layer_id)
            elif position == "out_of_group":
                if layer.parent_id is None:
                    raise ValidationError("Layer is not in a group")
                parent = doc.layers[layer.parent_id]
                doc.detach(layer_id)
                layer.parent_id = parent.parent_id
                target = doc.siblings(parent)
                target.insert(target.index(parent.id) + 1, layer_id)
            else:
                raise ValidationError("position must be up, down, top, bottom, above, below, into_group or out_of_group")
            tx.touch(layer_id)
        return self.result(proj, tx)

    def create_group(self, document_id: str, name: str, layer_ids: list[str] | None = None,
                     blend_mode: str = "pass_through", above: str | None = None) -> dict[str, Any]:
        proj = self.project(document_id)
        with proj.transaction("create_group", {"name": name, "layer_ids": layer_ids}) as tx:
            doc = tx.doc
            group = Layer(id=new_id("grp"), name=name, kind=LayerKind.group, width=doc.width, height=doc.height,
                          blend_mode=BlendMode(blend_mode))
            ids = layer_ids or []
            parents = {doc.layer(lid).parent_id for lid in ids}
            if len(parents) > 1:
                raise ValidationError("All layers to group must share the same parent")
            parent = parents.pop() if parents else None
            if ids:
                stack = doc.siblings(doc.layer(ids[0]))
                topmost = max(ids, key=stack.index)
                doc.insert(group, parent_id=parent, above=topmost)
                for lid in sorted(ids, key=stack.index):
                    doc.detach(lid)
                    doc.layers[lid].parent_id = group.id
                    group.children.append(lid)
            else:
                self._place(tx, group, above, None, None)
            tx.touch(group.id, *ids)
            tx.result["group_id"] = group.id
        return self.result(proj, tx)

    def merge_down(self, document_id: str, layer_id: str, name: str | None = None) -> dict[str, Any]:
        """Merge a layer into the layer directly below it (explicit, destructive; undo is available)."""
        proj = self.project(document_id)
        with proj.transaction("merge_down", {"layer_id": layer_id}) as tx:
            doc = tx.doc
            top = doc.layer(layer_id)
            stack = doc.siblings(top)
            i = stack.index(layer_id)
            if i == 0:
                raise ValidationError("No layer below to merge into")
            bottom = doc.layers[stack[i - 1]]
            for lay in (top, bottom):
                if lay.kind in (LayerKind.group, LayerKind.adjustment):
                    raise ValidationError("merge_down works on pixel layers; rasterize groups/adjustments first")
            self.check_editable(bottom)
            sub = doc.model_copy(deep=True)
            sub.root = [bottom.id, top.id]
            for lay in (sub.layers[bottom.id], sub.layers[top.id]):
                lay.parent_id = None
            sub.layers[bottom.id].visible = True
            sub.layers[bottom.id].opacity = 1.0
            sub.layers[bottom.id].blend_mode = BlendMode.normal
            sub.layers[bottom.id].clipped = False
            canvas = Compositor(sub, proj.blobs).render()
            rgba = f_to_u8(canvas)
            bbox = _opaque_bbox(rgba)
            if bbox is None:
                bbox = [0, 0, 1, 1]
            x0, y0, w, h = bbox
            bottom.pixels = proj.blobs.put(np.ascontiguousarray(rgba[y0:y0 + h, x0:x0 + w]))
            bottom.x, bottom.y, bottom.width, bottom.height = x0, y0, w, h
            bottom.mask = None
            bottom.effects = []
            bottom.base_blob = bottom.transform = None
            bottom.kind = LayerKind.raster
            if name:
                bottom.name = name
            doc.remove(layer_id)
            tx.touch(bottom.id)
            tx.warnings.append("Merged content outside the canvas was clipped")
            tx.result["layer_id"] = bottom.id
        return self.result(proj, tx)

    def flatten_image(self, document_id: str, background: str | None = "#ffffff") -> dict[str, Any]:
        """Explicitly flatten the whole document into one layer (destructive; undo is available)."""
        proj = self.project(document_id)
        canvas = self.render_doc(proj)
        with proj.transaction("flatten_image", {"background": background}) as tx:
            from ..core.compositor import flatten_to_u8
            arr = flatten_to_u8(canvas, background)
            tx.doc.layers.clear()
            tx.doc.root.clear()
            layer = Layer(id=new_id("lyr"), name="Flattened", width=tx.doc.width, height=tx.doc.height)
            layer.pixels = proj.blobs.put(arr)
            tx.doc.insert(layer)
            tx.touch(layer.id)
            tx.result["layer_id"] = layer.id
        return self.result(proj, tx)

    def rasterize_layer(self, document_id: str, layer_id: str) -> dict[str, Any]:
        """Convert text/shape/fill/smart layers into plain raster pixels."""
        proj = self.project(document_id)
        with proj.transaction("rasterize_layer", {"layer_id": layer_id}) as tx:
            layer = tx.doc.layer(layer_id)
            if layer.kind not in (LayerKind.text, LayerKind.shape, LayerKind.fill, LayerKind.raster):
                raise ValidationError("Only text, shape, fill or smart raster layers can be rasterized")
            layer.kind = LayerKind.raster
            layer.text = layer.shape = layer.fill = None
            layer.base_blob = layer.transform = None
            tx.touch(layer_id)
        return self.result(proj, tx)

    def blend_layers(self, document_id: str, top_layer_id: str, blend_mode: str = "normal", opacity: float = 1.0,
                     merge: bool = False) -> dict[str, Any]:
        """Set how a layer blends with what is below it; optionally merge it down."""
        res = self.set_layer_properties(document_id, top_layer_id, blend_mode=blend_mode, opacity=opacity)
        if merge:
            return self.merge_down(document_id, top_layer_id)
        return res


def composite_over(bottom: np.ndarray, top: np.ndarray, mode: str = "normal", opacity: float = 1.0) -> np.ndarray:
    return f_to_u8(composite(u8_to_f(bottom), u8_to_f(top), BlendMode(mode), opacity))
