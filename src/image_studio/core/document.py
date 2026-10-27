"""Document model: canvas, layer tree, assets, selection and metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..errors import NotFoundError, ValidationError
from .layer import Layer, LayerKind
from .provenance import Provenance


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Asset(BaseModel):
    id: str
    kind: str = Field("source", description="source | reference | generated | procedural")
    role: str = Field("composited", description="composited (used in the image) | reference_only")
    path: str  # relative to project root
    sha256: str
    width: int
    height: int
    format: str | None = None
    provenance: Provenance = Field(default_factory=Provenance)
    added_at: str = Field(default_factory=utcnow)


class HistoryEntry(BaseModel):
    id: str
    revision: int
    timestamp: str = Field(default_factory=utcnow)
    op: str
    params: dict[str, Any] = Field(default_factory=dict)
    affected_layers: list[str] = Field(default_factory=list)
    backend: str | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Checkpoint(BaseModel):
    id: str
    name: str
    revision: int
    created_at: str = Field(default_factory=utcnow)
    note: str | None = None


class Document(BaseModel):
    id: str
    name: str
    width: int
    height: int
    color_mode: str = "RGB"
    bit_depth: int = 8
    resolution_dpi: float = 72.0
    layers: dict[str, Layer] = Field(default_factory=dict)
    root: list[str] = Field(default_factory=list)  # bottom -> top
    assets: dict[str, Asset] = Field(default_factory=dict)
    selection: str | None = None  # blob hash of a document-sized L mask
    metadata: dict[str, Any] = Field(default_factory=dict)
    revision: int = 0
    created_at: str = Field(default_factory=utcnow)
    modified_at: str = Field(default_factory=utcnow)

    # ----- lookup -------------------------------------------------------
    def layer(self, layer_id: str) -> Layer:
        try:
            return self.layers[layer_id]
        except KeyError:
            raise NotFoundError(
                f"No layer with id '{layer_id}'.",
                hint="Call list_layers to get valid layer ids.",
                details={"valid_ids": list(self.layers)[:50]},
            ) from None

    def siblings(self, layer: Layer) -> list[str]:
        if layer.parent_id is None:
            return self.root
        return self.layers[layer.parent_id].children

    def walk(self, ids: list[str] | None = None, depth: int = 0):
        """Yield ``(layer, depth)`` top -> bottom, like a layers panel."""
        for lid in reversed(self.root if ids is None else ids):
            layer = self.layers[lid]
            yield layer, depth
            if layer.kind == LayerKind.group:
                yield from self.walk(layer.children, depth + 1)

    def descendants(self, layer_id: str) -> list[str]:
        layer = self.layer(layer_id)
        out: list[str] = []
        for cid in layer.children:
            out.append(cid)
            out.extend(self.descendants(cid))
        return out

    # ----- mutation -----------------------------------------------------
    def insert(self, layer: Layer, *, parent_id: str | None = None, above: str | None = None,
               index: int | None = None) -> None:
        if layer.id in self.layers:
            raise ValidationError(f"Layer id '{layer.id}' already exists")
        if parent_id is not None:
            parent = self.layer(parent_id)
            if parent.kind != LayerKind.group:
                raise ValidationError(f"Layer '{parent_id}' is not a group")
        layer.parent_id = parent_id
        self.layers[layer.id] = layer
        stack = self.siblings(layer)
        if above is not None:
            if above not in stack:
                raise ValidationError(f"Layer '{above}' is not a sibling in the target container")
            stack.insert(stack.index(above) + 1, layer.id)
        elif index is not None:
            stack.insert(max(0, min(index, len(stack))), layer.id)
        else:
            stack.append(layer.id)

    def detach(self, layer_id: str) -> Layer:
        layer = self.layer(layer_id)
        self.siblings(layer).remove(layer_id)
        return layer

    def remove(self, layer_id: str) -> list[str]:
        removed = [layer_id, *self.descendants(layer_id)]
        self.detach(layer_id)
        for lid in removed:
            self.layers.pop(lid, None)
        return removed

    def summary(self) -> dict[str, Any]:
        return {
            "document_id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "color_mode": self.color_mode,
            "bit_depth": self.bit_depth,
            "resolution_dpi": self.resolution_dpi,
            "revision": self.revision,
            "layer_count": len(self.layers),
            "has_selection": self.selection is not None,
            "asset_count": len(self.assets),
            "modified_at": self.modified_at,
        }
