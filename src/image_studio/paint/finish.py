"""Finishing passes: colour grade, vignette, film grain and colour washes (as separate layers)."""

from __future__ import annotations

import numpy as np

from .canvas import ColorLike, layer, rgb, smoothstep
from .noise import value_noise


def vignette(width: int, height: int, *, amount: float = 0.45, radius: float = 0.75, softness: float = 0.55,
             color: ColorLike = "#000000", center: tuple[float, float] = (0.5, 0.5)) -> np.ndarray:
    """Darkening toward the corners (use blend mode multiply or normal)."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    d = np.hypot((xs / width - center[0]) / 0.5, (ys / height - center[1]) / 0.5) / np.sqrt(2)
    a = smoothstep(radius - softness / 2, radius + softness / 2, d) * amount
    return layer(np.broadcast_to(rgb(color), (height, width, 3)).copy(), a)


def grain(width: int, height: int, *, amount: float = 0.06, size: float = 1.0, seed: int = 0) -> np.ndarray:
    """Neutral-grey film grain; blend with overlay/soft_light."""
    rng = np.random.default_rng(seed)
    if size > 1.2:
        g = value_noise(width, height, size, seed) - 0.5
    else:
        g = rng.normal(0, 0.5, (height, width)).astype(np.float32)
    v = np.clip(0.5 + g * amount * 2, 0, 1)
    return layer(np.repeat(v[..., None], 3, axis=2), 1.0)


def wash(width: int, height: int, color: ColorLike, *, top: float = 1.0, bottom: float = 1.0) -> np.ndarray:
    """Colour wash with a vertical opacity ramp (soft_light/color/overlay grading layers)."""
    a = np.linspace(top, bottom, height, dtype=np.float32)[:, None] * np.ones((1, width), np.float32)
    return layer(np.broadcast_to(rgb(color), (height, width, 3)).copy(), a)


def grade(img: np.ndarray, *, exposure: float = 0.0, contrast: float = 0.0, saturation: float = 0.0,
          temperature: float = 0.0, lift: ColorLike | None = None, lift_amount: float = 0.0) -> np.ndarray:
    """Quick global grade on an (H, W, 3/4) image (for direct pipeline use; prefer adjustment layers)."""
    out = img.copy()
    c = out[..., :3] * (2 ** exposure)
    if contrast:
        c = 0.5 + (c - 0.5) * (1 + contrast)
    if saturation:
        lum = (c @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        c = lum + (c - lum) * (1 + saturation)
    if temperature:
        c = c * np.array([1 + temperature * 0.1, 1, 1 - temperature * 0.1], np.float32)
    if lift is not None and lift_amount:
        c = c + (rgb(lift) - c) * lift_amount * (1 - c)
    out[..., :3] = np.clip(c, 0, 1)
    return out
