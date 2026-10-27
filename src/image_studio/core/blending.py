"""Blend modes and W3C "source-over" compositing on float RGBA arrays.

Formulas follow the W3C Compositing and Blending Level 1 specification
(https://www.w3.org/TR/compositing-1/), which is also what GIMP's and
Photoshop's legacy modes approximate for 8-bit sRGB.
"""

from __future__ import annotations

import numpy as np

from .color import luminance
from .layer import BlendMode

EPS = 1e-6


def _soft_light(cb, cs):
    d = np.where(cb <= 0.25, ((16 * cb - 12) * cb + 4) * cb, np.sqrt(cb))
    return np.where(cs <= 0.5, cb - (1 - 2 * cs) * cb * (1 - cb), cb + (2 * cs - 1) * (d - cb))


def _hard_light(cb, cs):
    return np.where(cs <= 0.5, cb * 2 * cs, 1 - (1 - cb) * (1 - (2 * cs - 1)))


def _lum(c):
    return luminance(c)[..., None]


def _clip_color(c):
    lum = _lum(c)
    n = c.min(axis=-1, keepdims=True)
    x = c.max(axis=-1, keepdims=True)
    c = np.where(n < 0, lum + (c - lum) * lum / np.maximum(lum - n, EPS), c)
    c = np.where(x > 1, lum + (c - lum) * (1 - lum) / np.maximum(x - lum, EPS), c)
    return c


def _set_lum(c, lum):
    return _clip_color(c + (lum - _lum(c)))


def _sat(c):
    return c.max(axis=-1, keepdims=True) - c.min(axis=-1, keepdims=True)


def _set_sat(c, s):
    cmax = c.max(axis=-1, keepdims=True)
    cmin = c.min(axis=-1, keepdims=True)
    rng = cmax - cmin
    return np.where(rng > EPS, (c - cmin) * s / np.maximum(rng, EPS), 0.0)


def blend_function(mode: BlendMode, cb: np.ndarray, cs: np.ndarray) -> np.ndarray:
    """Return B(cb, cs) for RGB arrays in 0..1."""
    m = mode
    if m in (BlendMode.normal, BlendMode.pass_through):
        return cs
    if m == BlendMode.multiply:
        return cb * cs
    if m == BlendMode.screen:
        return cb + cs - cb * cs
    if m == BlendMode.overlay:
        return _hard_light(cs, cb)
    if m == BlendMode.soft_light:
        return _soft_light(cb, cs)
    if m == BlendMode.hard_light:
        return _hard_light(cb, cs)
    if m == BlendMode.darken:
        return np.minimum(cb, cs)
    if m == BlendMode.lighten:
        return np.maximum(cb, cs)
    if m == BlendMode.color_dodge:
        return np.where(cb <= 0, 0.0, np.where(cs >= 1, 1.0, np.minimum(1.0, cb / np.maximum(1 - cs, EPS))))
    if m == BlendMode.color_burn:
        return np.where(cb >= 1, 1.0, np.where(cs <= 0, 0.0, 1 - np.minimum(1.0, (1 - cb) / np.maximum(cs, EPS))))
    if m == BlendMode.linear_dodge:
        return np.minimum(1.0, cb + cs)
    if m == BlendMode.linear_burn:
        return np.maximum(0.0, cb + cs - 1)
    if m == BlendMode.difference:
        return np.abs(cb - cs)
    if m == BlendMode.exclusion:
        return cb + cs - 2 * cb * cs
    if m == BlendMode.subtract:
        return np.maximum(0.0, cb - cs)
    if m == BlendMode.divide:
        return np.minimum(1.0, cb / np.maximum(cs, EPS))
    if m == BlendMode.hue:
        return _set_lum(_set_sat(cs, _sat(cb)), _lum(cb))
    if m == BlendMode.saturation:
        return _set_lum(_set_sat(cb, _sat(cs)), _lum(cb))
    if m == BlendMode.color:
        return _set_lum(cs, _lum(cb))
    if m == BlendMode.luminosity:
        return _set_lum(cb, _lum(cs))
    raise ValueError(f"Unknown blend mode {mode}")


def composite(backdrop: np.ndarray, source: np.ndarray, mode: BlendMode = BlendMode.normal,
              opacity: float = 1.0, mask: np.ndarray | None = None) -> np.ndarray:
    """Composite ``source`` over ``backdrop`` (both float RGBA, straight alpha). Returns new array."""
    cb, ab = backdrop[..., :3], backdrop[..., 3:4]
    cs, a_s = source[..., :3], source[..., 3:4] * opacity
    if mask is not None:
        a_s = a_s * mask[..., None]
    mixed = (1 - ab) * cs + ab * np.clip(blend_function(mode, cb, cs), 0, 1)
    ao = a_s + ab * (1 - a_s)
    co = a_s * mixed + ab * cb * (1 - a_s)
    out = np.empty_like(backdrop)
    out[..., :3] = np.where(ao > EPS, co / np.maximum(ao, EPS), 0.0)
    out[..., 3:4] = ao
    return out


def lerp_rgba(a: np.ndarray, b: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    if isinstance(t, np.ndarray) and t.ndim == 2:
        t = t[..., None]
    return a + (b - a) * t
