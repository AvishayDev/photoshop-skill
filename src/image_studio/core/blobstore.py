"""Content-addressed pixel storage.

Pixel data lives in immutable PNG files named by the SHA-256 of their raw
array. Because blobs never change, a revision snapshot or checkpoint is just a
small JSON manifest that references blob hashes; undo never copies pixels.
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image

from ..errors import NotFoundError, ValidationError


def array_hash(arr: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(str(arr.shape).encode())
    h.update(str(arr.dtype).encode())
    h.update(np.ascontiguousarray(arr).tobytes())
    return h.hexdigest()[:40]


class BlobStore:
    def __init__(self, root: Path, cache_items: int = 48):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_items = cache_items

    def path(self, blob: str) -> Path:
        if not blob or not all(c in "0123456789abcdef" for c in blob):
            raise ValidationError(f"Invalid blob id {blob!r}")
        return self.root / blob[:2] / f"{blob}.png"

    def put(self, arr: np.ndarray) -> str:
        if arr.dtype != np.uint8:
            raise ValidationError(f"Blob arrays must be uint8, got {arr.dtype}")
        if arr.ndim == 3 and arr.shape[2] == 4:
            mode = "RGBA"
        elif arr.ndim == 2:
            mode = "L"
        else:
            raise ValidationError(f"Unsupported blob shape {arr.shape}")
        if arr.shape[0] == 0 or arr.shape[1] == 0:
            raise ValidationError("Cannot store an empty image")
        blob = array_hash(arr)
        target = self.path(blob)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(f".tmp{os.getpid()}")
            Image.fromarray(arr, mode).save(tmp, format="PNG", compress_level=3)
            os.replace(tmp, target)
        self._remember(blob, arr)
        return blob

    def get(self, blob: str) -> np.ndarray:
        if blob in self._cache:
            self._cache.move_to_end(blob)
            return self._cache[blob].copy()
        p = self.path(blob)
        if not p.exists():
            raise NotFoundError(f"Pixel blob {blob} is missing from the project store",
                                hint="The project may be corrupted; restore a checkpoint.")
        with Image.open(p) as im:
            im.load()
            arr = np.asarray(im.convert(im.mode if im.mode in ("RGBA", "L") else "RGBA")).copy()
        self._remember(blob, arr)
        return arr.copy()

    def _remember(self, blob: str, arr: np.ndarray) -> None:
        self._cache[blob] = arr
        self._cache.move_to_end(blob)
        while len(self._cache) > self._cache_items:
            self._cache.popitem(last=False)

    def all_blobs(self) -> set[str]:
        return {p.stem for p in self.root.glob("*/*.png")}

    def delete(self, blob: str) -> None:
        self._cache.pop(blob, None)
        self.path(blob).unlink(missing_ok=True)
