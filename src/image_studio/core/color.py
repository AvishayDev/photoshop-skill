"""Color parsing and conversion helpers (sRGB, 8-bit)."""

from __future__ import annotations

import re

import cv2
import numpy as np

from ..errors import ValidationError

_NAMED = {
    "white": "#ffffff", "black": "#000000", "red": "#ff0000", "green": "#00ff00", "blue": "#0000ff",
    "yellow": "#ffff00", "cyan": "#00ffff", "magenta": "#ff00ff", "gray": "#808080", "grey": "#808080",
    "orange": "#ff8000", "transparent": "#00000000",
}
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def parse_color(value: str | list | tuple) -> tuple[int, int, int, int]:
    """Parse '#rgb', '#rrggbb', '#rrggbbaa', a CSS-like name, or an [r, g, b(, a)] list."""
    if isinstance(value, (list, tuple)):
        if len(value) not in (3, 4) or not all(isinstance(c, (int, float)) for c in value):
            raise ValidationError(f"Color list must have 3 or 4 numbers, got {value!r}")
        vals = [int(round(c)) for c in value] + ([255] if len(value) == 3 else [])
        if not all(0 <= c <= 255 for c in vals):
            raise ValidationError("Color components must be 0..255")
        return tuple(vals)  # type: ignore[return-value]
    s = _NAMED.get(str(value).strip().lower(), str(value).strip())
    m = _HEX_RE.match(s)
    if not m:
        raise ValidationError(f"Cannot parse color {value!r}; use '#rrggbb' or '#rrggbbaa'")
    h = m.group(1)
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        h += "ff"
    return tuple(int(h[i:i + 2], 16) for i in range(0, 8, 2))  # type: ignore[return-value]


def to_hex(rgb) -> str:
    return "#" + "".join(f"{int(max(0, min(255, round(c)))):02x}" for c in rgb[:3])


def u8_to_f(arr: np.ndarray) -> np.ndarray:
    return arr.astype(np.float32) / 255.0


def f_to_u8(arr: np.ndarray) -> np.ndarray:
    return np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8)


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec. 709 luma of float RGB in 0..1."""
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb.astype(np.float32)), cv2.COLOR_RGB2HSV)
    hsv[..., 0] /= 360.0
    return hsv


def hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    h = hsv.astype(np.float32).copy()
    h[..., 0] = (h[..., 0] % 1.0) * 360.0
    return cv2.cvtColor(np.ascontiguousarray(h), cv2.COLOR_HSV2RGB)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.ascontiguousarray(rgb.astype(np.float32)), cv2.COLOR_RGB2LAB)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(cv2.cvtColor(np.ascontiguousarray(lab.astype(np.float32)), cv2.COLOR_LAB2RGB), 0, 1)
