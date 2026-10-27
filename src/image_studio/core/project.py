"""On-disk project: manifest, blobs, revisions, checkpoints and history.

Layout::

    <workspace>/<slug>/
        project.json        current manifest (document + history + checkpoints)
        blobs/              immutable content-addressed pixel data
        revisions/<n>.json  document snapshot after revision n (enables undo)
        assets/             imported originals (never modified)
        references/         research thumbnails + provenance sidecars
        research/           research notes and observations
        plans/              submitted plans
        previews/           rendered previews
        exports/            final exports

Every mutating operation runs inside :meth:`Project.transaction`. The working
copy of the document is only committed (atomically, via ``os.replace``) when
the operation succeeds, so a failing operation never leaves a half-edited
project behind.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import get_settings
from ..errors import NotFoundError, StudioError, ValidationError
from ..security import safe_child, slugify
from .blobstore import BlobStore
from .document import Checkpoint, Document, HistoryEntry, utcnow
from .ids import new_id

FORMAT_VERSION = 1


class Manifest(BaseModel):
    format_version: int = FORMAT_VERSION
    tool: str = "agent-image-studio"
    document: Document
    history: list[HistoryEntry] = Field(default_factory=list)
    checkpoints: dict[str, Checkpoint] = Field(default_factory=dict)
    plans: list[str] = Field(default_factory=list)


def _atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class Project:
    SUBDIRS = ("blobs", "revisions", "assets", "references", "research", "plans", "previews", "exports")

    def __init__(self, root: Path, manifest: Manifest):
        self.root = root
        self.manifest = manifest
        self.blobs = BlobStore(root / "blobs")
        self._pending: dict[str, Any] | None = None

    # ----- construction ---------------------------------------------------
    @classmethod
    def create(cls, name: str, width: int, height: int, *, workspace: Path | None = None,
               resolution_dpi: float = 72.0) -> Project:
        if not (1 <= width <= 30000 and 1 <= height <= 30000):
            raise ValidationError("Canvas dimensions must be between 1 and 30000 pixels")
        if width * height > get_settings().max_image_pixels:
            raise ValidationError("Canvas exceeds IMAGE_STUDIO_MAX_PIXELS")
        workspace = workspace or get_settings().workspace
        workspace.mkdir(parents=True, exist_ok=True)
        slug = slugify(name)
        root = workspace / slug
        n = 2
        while root.exists():
            root = workspace / f"{slug}-{n}"
            n += 1
        root.mkdir(parents=True)
        for sub in cls.SUBDIRS:
            (root / sub).mkdir()
        doc = Document(id=new_id("doc"), name=name, width=width, height=height, resolution_dpi=resolution_dpi)
        proj = cls(root, Manifest(document=doc))
        proj._write_revision()
        proj.save()
        return proj

    @classmethod
    def load(cls, root: Path) -> Project:
        mf = root / "project.json"
        if not mf.exists():
            raise NotFoundError(f"No project.json in {root}")
        try:
            manifest = Manifest.model_validate_json(mf.read_text(encoding="utf-8"))
        except Exception as exc:
            raise StudioError(f"Project manifest is unreadable: {exc}",
                              hint="Restore the previous revision from revisions/ or a checkpoint.") from exc
        if manifest.format_version > FORMAT_VERSION:
            raise ValidationError("Project was written by a newer version of agent-image-studio")
        return cls(root, manifest)

    # ----- properties -----------------------------------------------------
    @property
    def doc(self) -> Document:
        return self.manifest.document

    @property
    def id(self) -> str:
        return self.doc.id

    def path(self, *parts: str) -> Path:
        return safe_child(self.root, *parts)

    # ----- persistence ----------------------------------------------------
    def save(self) -> Path:
        self.doc.modified_at = utcnow()
        path = self.root / "project.json"
        _atomic_write_json(path, self.manifest.model_dump(mode="json"))
        return path

    def _write_revision(self) -> None:
        _atomic_write_json(self.root / "revisions" / f"{self.doc.revision}.json",
                           self.doc.model_dump(mode="json"))
        self._prune_revisions()

    def _prune_revisions(self) -> None:
        keep = get_settings().max_revisions
        pinned = {c.revision for c in self.manifest.checkpoints.values()}
        revs = sorted(int(p.stem) for p in (self.root / "revisions").glob("*.json") if p.stem.isdigit())
        for r in revs[:-keep] if len(revs) > keep else []:
            if r not in pinned:
                (self.root / "revisions" / f"{r}.json").unlink(missing_ok=True)

    def load_revision(self, revision: int) -> Document:
        p = self.root / "revisions" / f"{revision}.json"
        if not p.exists():
            raise NotFoundError(f"Revision {revision} is not available (it may have been pruned).")
        return Document.model_validate_json(p.read_text(encoding="utf-8"))

    def available_revisions(self) -> list[int]:
        return sorted(int(p.stem) for p in (self.root / "revisions").glob("*.json") if p.stem.isdigit())

    # ----- transactions ---------------------------------------------------
    @contextlib.contextmanager
    def transaction(self, op: str, params: dict[str, Any] | None = None, *, backend: str | None = None):
        """Run a mutation on a working copy and commit it atomically.

        Yields a :class:`TxContext` whose ``doc`` must be mutated. Raise to abort.
        """
        working = self.doc.model_copy(deep=True)
        ctx = TxContext(working)
        yield ctx
        working.revision = self.doc.revision + 1
        working.modified_at = utcnow()
        entry = HistoryEntry(
            id=new_id("op"), revision=working.revision, op=op, params=_sanitize(params or {}),
            affected_layers=ctx.affected, backend=backend or ctx.backend, message=ctx.message,
            warnings=ctx.warnings,
        )
        self.manifest.document = working
        self.manifest.history.append(entry)
        if len(self.manifest.history) > 2000:
            self.manifest.history = self.manifest.history[-2000:]
        self._write_revision()
        self.save()
        ctx.entry = entry

    # ----- checkpoints / undo ---------------------------------------------
    def create_checkpoint(self, name: str, note: str | None = None) -> Checkpoint:
        cp = Checkpoint(id=new_id("ckpt"), name=name, revision=self.doc.revision, note=note)
        self.manifest.checkpoints[cp.id] = cp
        self.save()
        return cp

    def resolve_checkpoint(self, ref: str) -> Checkpoint:
        if ref in self.manifest.checkpoints:
            return self.manifest.checkpoints[ref]
        for cp in self.manifest.checkpoints.values():
            if cp.name == ref:
                return cp
        raise NotFoundError(f"No checkpoint '{ref}'", details={
            "checkpoints": [c.model_dump() for c in self.manifest.checkpoints.values()]})

    def restore_revision(self, revision: int, *, op: str = "restore_revision", params: dict | None = None):
        snapshot = self.load_revision(revision)
        missing = [b for b in _referenced_blobs(snapshot) if not self.blobs.path(b).exists()]
        if missing:
            raise StudioError(f"Cannot restore revision {revision}: {len(missing)} pixel blobs are missing")
        with self.transaction(op, params or {"revision": revision}) as tx:
            data = snapshot.model_dump()
            data["revision"] = tx.doc.revision
            data["created_at"] = tx.doc.created_at
            restored = Document.model_validate(data)
            for field in Document.model_fields:
                setattr(tx.doc, field, getattr(restored, field))
            tx.message = f"Restored state of revision {revision}"
        return tx

    def undo(self, steps: int = 1):
        if steps < 1:
            raise ValidationError("steps must be >= 1")
        target = self.doc.revision - steps
        if target < 0:
            raise ValidationError("Nothing to undo that far back")
        return self.restore_revision(target, op="undo", params={"steps": steps, "to_revision": target})

    # ----- maintenance ----------------------------------------------------
    def garbage_collect(self) -> dict[str, int]:
        referenced: set[str] = set(_referenced_blobs(self.doc))
        for rev in self.available_revisions():
            with contextlib.suppress(Exception):
                referenced |= set(_referenced_blobs(self.load_revision(rev)))
        removed = 0
        for blob in self.blobs.all_blobs() - referenced:
            self.blobs.delete(blob)
            removed += 1
        return {"removed_blobs": removed, "kept_blobs": len(referenced)}


class TxContext:
    def __init__(self, doc: Document):
        self.doc = doc
        self.affected: list[str] = []
        self.warnings: list[str] = []
        self.message: str | None = None
        self.backend: str | None = None
        self.entry: HistoryEntry | None = None
        self.result: dict[str, Any] = {}

    def touch(self, *layer_ids: str) -> None:
        for lid in layer_ids:
            if lid not in self.affected:
                self.affected.append(lid)


def _referenced_blobs(doc: Document) -> list[str]:
    out = []
    for layer in doc.layers.values():
        for b in (layer.pixels, layer.base_blob, layer.mask.blob if layer.mask else None):
            if b:
                out.append(b)
    if doc.selection:
        out.append(doc.selection)
    return out


def _sanitize(params: dict[str, Any]) -> dict[str, Any]:
    """Keep history readable: truncate long lists/strings."""
    out: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str) and len(v) > 500:
            v = v[:500] + "..."
        elif isinstance(v, list) and len(v) > 50:
            v = [*v[:50], f"... ({len(v)} items)"]
        out[k] = v
    return out
