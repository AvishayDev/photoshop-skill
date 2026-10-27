from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class ImageGenerator(ABC):
    name = "base"

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """{'available': bool, 'detail': str, 'how_to_enable': str | None, 'models': [...]}"""

    @abstractmethod
    def generate(self, *, prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024,
                 seed: int | None = None, steps: int = 25, cfg: float = 6.5) -> tuple[np.ndarray, dict[str, Any]]:
        """Return (RGBA uint8 array, metadata including model, seed and parameters)."""
