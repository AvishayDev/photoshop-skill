"""Built-in raster backend (Pillow + NumPy + OpenCV).

Always available. Provides the filters in :mod:`image_studio.core.filters`,
clone stamp and healing from :mod:`image_studio.core.retouch`, and layered
OpenRaster (.ora) read/write. It cannot read or write XCF/PSD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import PIL

from ...core import filters as core_filters
from ...core import retouch
from ...core.color import f_to_u8, u8_to_f
from ...formats import ora
from ..base import (
    CAP_CLONE,
    CAP_EXPORT_NATIVE,
    CAP_FILTER,
    CAP_HEAL,
    CAP_IMPORT_NATIVE,
    Backend,
    BackendStatus,
    ImportedDocument,
)


class PillowBackend(Backend):
    name = "pillow"

    def status(self) -> BackendStatus:
        return BackendStatus(name=self.name, available=True,
                             version=f"Pillow {PIL.__version__}, NumPy {np.__version__}, OpenCV {cv2.__version__}",
                             native_formats=["ora"],
                             detail="Built-in raster engine; always available.")

    def capabilities(self) -> set[str]:
        return {CAP_FILTER, CAP_CLONE, CAP_HEAL, CAP_EXPORT_NATIVE, CAP_IMPORT_NATIVE}

    def filters(self) -> list[str]:
        return sorted(core_filters.FILTERS)

    def apply_filter(self, rgba: np.ndarray, name: str, params: dict[str, Any]) -> np.ndarray:
        return f_to_u8(core_filters.apply_filter(u8_to_f(rgba), name, params))

    def clone_stamp(self, target, source, **kw):
        return retouch.clone_stamp(target, source, **kw)

    def heal(self, target, **kw):
        return retouch.heal(target, **kw)

    def export_native(self, spec: dict[str, Any], out_path: Path, fmt: str) -> dict[str, Any]:
        if fmt != "ora":
            return super().export_native(spec, out_path, fmt)
        return ora.write_ora(spec, out_path)

    def import_native(self, path: Path, work_dir: Path) -> ImportedDocument:
        if path.suffix.lower() != ".ora":
            return super().import_native(path, work_dir)
        return ora.read_ora(path, work_dir)
