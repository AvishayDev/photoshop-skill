"""Colour helpers and straight-alpha compositing on float32 RGBA canvases."""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from ..core.color import parse_color

ColorLike = str | Sequence[float]


def rgb(color: ColorLike) -> np.ndarray:
    """'#rrggbb' / name / [r, g, b] (0..255) -> float32 (3,) in 0..1."""
    return np.array(parse_color(color)[:3], np.float32) / 255.0


def rgba(color: ColorLike) -> np.ndarray:
    return np.array(parse_color(color), np.float32) / 255.0


def blank(width: int, height: int) -> np.ndarray:
    return np.zeros((height, width, 4), np.float32)


def solid(width: int, height: int, color: ColorLike, alpha: np.ndarray | float = 1.0) -> np.ndarray:
    out = np.empty((height, width, 4), np.float32)
    out[..., :3] = rgb(color)
    out[..., 3] = alpha
    return out


def layer(rgb_img: np.ndarray, alpha: np.ndarray | float = 1.0) -> np.ndarray:
    """Stack an (H, W, 3) colour image and an alpha mask into RGBA."""
    h, w = rgb_img.shape[:2]
    out = np.empty((h, w, 4), np.float32)
    out[..., :3] = np.clip(rgb_img, 0, 1)
    out[..., 3] = np.clip(alpha, 0, 1)
    return out


def over(dst: np.ndarray, src: np.ndarray, opacity: float = 1.0) -> np.ndarray:
    """Porter-Duff source-over of straight-alpha RGBA images (returns a new array)."""
    sa = src[..., 3:4] * opacity
    da = dst[..., 3:4]
    oa = sa + da * (1 - sa)
    rgb_ = (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    return np.concatenate([rgb_, oa], axis=-1).astype(np.float32)


def merge(layers: Sequence[np.ndarray]) -> np.ndarray:
    out = np.zeros_like(layers[0])
    for lyr in layers:
        out = over(out, lyr)
    return out


def mix(a: np.ndarray, b: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    t = np.asarray(t, np.float32)
    if t.ndim == 2 and a.ndim == 3:
        t = t[..., None]
    return a + (b - a) * t


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    d = e1 - e0
    t = np.clip((x - e0) / (d if abs(d) > 1e-9 else 1e-9), 0, 1)  # e0 > e1 gives a falling edge
    return t * t * (3 - 2 * t)


def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return img
    return cv2.GaussianBlur(img, (0, 0), float(sigma))


def ramp(t: np.ndarray, colors: Sequence[ColorLike], positions: Sequence[float] | None = None) -> np.ndarray:
    """Map a 0..1 field through a multi-stop colour gradient -> (..., 3)."""
    cols = np.stack([rgb(c) for c in colors])
    pos = np.asarray(positions if positions is not None else np.linspace(0, 1, len(cols)), np.float32)
    t = np.clip(np.asarray(t, np.float32), 0, 1)
    out = np.empty(t.shape + (3,), np.float32)
    for ch in range(3):
        out[..., ch] = np.interp(t, pos, cols[:, ch])
    return out


def luminance(img: np.ndarray) -> np.ndarray:
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722


def to_u8(img: np.ndarray) -> np.ndarray:
    return np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)


def from_u8(img: np.ndarray) -> np.ndarray:
    return img.astype(np.float32) / 255.0


def place(small: np.ndarray, width: int, height: int, x: int, y: int) -> np.ndarray:
    """Paste a small RGBA image into a transparent full canvas at (x, y), clipping at the edges."""
    out = blank(width, height)
    h, w = small.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(width, x + w), min(height, y + h)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = small[y0 - y:y1 - y, x0 - x:x1 - x]
    return out
