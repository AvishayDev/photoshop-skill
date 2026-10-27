"""Backend interface.

The document model, history and compositing live in ``image_studio.core`` and
are backend-independent. A backend contributes *operations* on pixel data and
native file formats. Each backend advertises exactly which operations it can
perform via :meth:`Backend.capabilities`; the editor never routes an operation
to a backend that has not advertised it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..errors import UnsupportedOperationError

# Operation capability names used for routing and reporting.
CAP_FILTER = "filter"                 # apply_filter with backend-specific filter names
CAP_CLONE = "clone_stamp"
CAP_HEAL = "heal"
CAP_EXPORT_NATIVE = "export_native"   # layered native file (ORA, XCF, PSD)
CAP_IMPORT_NATIVE = "import_native"   # read layered native file


@dataclass
class BackendStatus:
    name: str
    available: bool
    version: str | None = None
    native_formats: list[str] = field(default_factory=list)
    detail: str = ""
    missing: list[str] = field(default_factory=list)
    how_to_enable: str | None = None
    verified: bool = True  # False = implemented against documentation but not verified in CI

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ImportedLayer:
    name: str
    kind: str
    x: int
    y: int
    png: Path | None
    visible: bool = True
    opacity: float = 1.0
    blend_mode: str = "normal"
    mask_png: Path | None = None
    mask_enabled: bool = True
    text: str | None = None
    children: list[ImportedLayer] = field(default_factory=list)  # top -> bottom


@dataclass
class ImportedDocument:
    width: int
    height: int
    layers: list[ImportedLayer]  # top -> bottom
    resolution: float = 72.0
    warnings: list[str] = field(default_factory=list)


class Backend(ABC):
    name: str = "base"

    @abstractmethod
    def status(self) -> BackendStatus: ...

    @abstractmethod
    def capabilities(self) -> set[str]: ...

    def supports(self, cap: str) -> bool:
        return cap in self.capabilities() and self.status().available

    def filters(self) -> list[str]:
        return []

    # ----- optional operations (raise unless implemented) --------------------
    def apply_filter(self, rgba: np.ndarray, name: str, params: dict[str, Any]) -> np.ndarray:
        raise UnsupportedOperationError(f"Backend '{self.name}' cannot apply filters")

    def clone_stamp(self, target: np.ndarray, source: np.ndarray, **kwargs) -> tuple[np.ndarray, dict]:
        raise UnsupportedOperationError(f"Backend '{self.name}' has no clone stamp")

    def heal(self, target: np.ndarray, **kwargs) -> tuple[np.ndarray, dict]:
        raise UnsupportedOperationError(f"Backend '{self.name}' has no healing tool")

    def export_native(self, spec: dict[str, Any], out_path: Path, fmt: str) -> dict[str, Any]:
        raise UnsupportedOperationError(f"Backend '{self.name}' cannot write native project files")

    def import_native(self, path: Path, work_dir: Path) -> ImportedDocument:
        raise UnsupportedOperationError(f"Backend '{self.name}' cannot read layered files")
