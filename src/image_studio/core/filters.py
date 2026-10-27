"""Raster filters implemented with NumPy/OpenCV.

Filters operate on float RGBA (straight alpha). Blurs are computed on
premultiplied color so transparent pixels don't bleed dark fringes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

from ..errors import ValidationError
from .adjustments import Param
from .color import luminance


def _premul(rgba):
    out = rgba.copy()
    out[..., :3] *= rgba[..., 3:4]
    return out


def _unpremul(rgba):
    out = rgba.copy()
    a = rgba[..., 3:4]
    out[..., :3] = np.where(a > 1e-6, rgba[..., :3] / np.maximum(a, 1e-6), 0)
    return np.clip(out, 0, 1)


def _blur_premul(rgba, fn):
    return _unpremul(fn(_premul(rgba)))


def gaussian_blur(rgba, radius=4.0):
    if radius <= 0:
        return rgba
    sigma = radius / 2.0
    return _blur_premul(rgba, lambda a: cv2.GaussianBlur(a, (0, 0), sigmaX=sigma, sigmaY=sigma,
                                                         borderType=cv2.BORDER_REPLICATE))


def box_blur(rgba, radius=3):
    k = max(1, int(radius) * 2 + 1)
    return _blur_premul(rgba, lambda a: cv2.blur(a, (k, k), borderType=cv2.BORDER_REPLICATE))


def motion_blur(rgba, distance=20.0, angle=0.0):
    n = max(3, int(distance) | 1)
    kernel = np.zeros((n, n), np.float32)
    kernel[n // 2, :] = 1.0
    rot = cv2.getRotationMatrix2D((n / 2 - 0.5, n / 2 - 0.5), angle, 1.0)
    kernel = cv2.warpAffine(kernel, rot, (n, n))
    kernel /= max(kernel.sum(), 1e-6)
    return _blur_premul(rgba, lambda a: cv2.filter2D(a, -1, kernel, borderType=cv2.BORDER_REPLICATE))


def lens_blur(rgba, radius=6.0, highlight_boost=0.0):
    """Disk-kernel (bokeh-like) blur; optional highlight boost emulates bright bokeh discs."""
    r = max(1, int(radius))
    k = np.zeros((2 * r + 1, 2 * r + 1), np.float32)
    cv2.circle(k, (r, r), r, 1.0, -1, lineType=cv2.LINE_AA)
    k /= k.sum()
    def run(a):
        if highlight_boost > 0:
            a = a.copy()
            a[..., :3] = a[..., :3] ** (1 + highlight_boost)
        b = cv2.filter2D(a, -1, k, borderType=cv2.BORDER_REPLICATE)
        if highlight_boost > 0:
            b[..., :3] = np.clip(b[..., :3], 0, None) ** (1 / (1 + highlight_boost))
        return b
    return _blur_premul(rgba, run)


def unsharp_mask(rgba, radius=2.0, amount=0.8, threshold=0.0):
    blurred = cv2.GaussianBlur(rgba[..., :3], (0, 0), max(radius / 2, 0.3))
    detail = rgba[..., :3] - blurred
    if threshold > 0:
        detail = np.where(np.abs(detail) * 255 >= threshold, detail, 0)
    out = rgba.copy()
    out[..., :3] = np.clip(rgba[..., :3] + detail * amount, 0, 1)
    return out


def high_pass(rgba, radius=3.0):
    blurred = cv2.GaussianBlur(rgba[..., :3], (0, 0), max(radius / 2, 0.3))
    out = rgba.copy()
    out[..., :3] = np.clip(rgba[..., :3] - blurred + 0.5, 0, 1)
    return out


def add_noise(rgba, amount=0.04, monochrome=True, seed=0, grain_size=1.0):
    """Film-grain style gaussian noise (amount = standard deviation in 0..1)."""
    rng = np.random.default_rng(seed)
    h, w = rgba.shape[:2]
    sh, sw = max(1, int(h / grain_size)), max(1, int(w / grain_size))
    shape = (sh, sw, 1) if monochrome else (sh, sw, 3)
    noise = rng.normal(0, amount, shape).astype(np.float32)
    if (sh, sw) != (h, w):
        noise = cv2.resize(noise, (w, h), interpolation=cv2.INTER_LINEAR)
        if noise.ndim == 2:
            noise = noise[..., None]
    out = rgba.copy()
    out[..., :3] = np.clip(rgba[..., :3] + noise, 0, 1)
    return out


def denoise(rgba, strength=6.0):
    u8 = (np.clip(rgba[..., :3], 0, 1) * 255).astype(np.uint8)
    res = cv2.fastNlMeansDenoisingColored(u8, None, float(strength), float(strength), 7, 21)
    out = rgba.copy()
    out[..., :3] = res.astype(np.float32) / 255
    return out


def median(rgba, radius=2):
    k = max(1, int(radius)) * 2 + 1
    u8 = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    return cv2.medianBlur(u8, min(k, 255)).astype(np.float32) / 255


def emboss(rgba, strength=1.0, angle=135.0):
    gray = luminance(rgba[..., :3])
    rad = np.deg2rad(angle)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    e = np.clip(0.5 + (gx * np.cos(rad) + gy * np.sin(rad)) * 0.25 * strength, 0, 1)
    out = rgba.copy()
    out[..., :3] = e[..., None]
    return out


def edge_detect(rgba, low=50, high=150):
    u8 = (luminance(np.clip(rgba[..., :3], 0, 1)) * 255).astype(np.uint8)
    edges = cv2.Canny(u8, int(low), int(high)).astype(np.float32) / 255
    out = rgba.copy()
    out[..., :3] = edges[..., None]
    return out


def vignette(rgba, amount=0.4, radius=0.75, softness=0.5, center=(0.5, 0.5)):
    h, w = rgba.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = center[0] * w, center[1] * h
    d = np.sqrt(((xx - cx) / (w / 2)) ** 2 + ((yy - cy) / (h / 2)) ** 2) / np.sqrt(2) * 1.414
    t = np.clip((d - radius) / max(softness, 1e-3), 0, 1)
    t = t * t * (3 - 2 * t)
    out = rgba.copy()
    out[..., :3] = rgba[..., :3] * (1 - amount * t[..., None])
    return out


def pixelate(rgba, cell=8):
    h, w = rgba.shape[:2]
    c = max(1, int(cell))
    small = cv2.resize(rgba, (max(1, w // c), max(1, h // c)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def chromatic_aberration(rgba, shift=2.0):
    h, w = rgba.shape[:2]
    out = rgba.copy()
    for ch, s in ((0, 1 + shift / max(w, h)), (2, 1 - shift / max(w, h))):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, s)
        out[..., ch] = cv2.warpAffine(rgba[..., ch], m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    return out


def gradient_blur(rgba, radius=8.0, focus_y=0.5, focus_band=0.2, falloff=0.3, angle=0.0):
    """Tilt-shift / depth-of-field approximation: blur grows away from a focus band."""
    h, w = rgba.shape[:2]
    blurred = gaussian_blur(rgba, radius)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rad = np.deg2rad(angle)
    coord = ((yy / h - 0.5) * np.cos(rad) - (xx / w - 0.5) * np.sin(rad)) + 0.5
    dist = np.abs(coord - focus_y) - focus_band / 2
    t = np.clip(dist / max(falloff, 1e-3), 0, 1)[..., None]
    return rgba * (1 - t) + blurred * t


def bloom(rgba, threshold=0.75, radius=12.0, intensity=0.6):
    lum = luminance(rgba[..., :3])
    bright = rgba[..., :3] * np.clip((lum - threshold) / max(1 - threshold, 1e-3), 0, 1)[..., None]
    glow = cv2.GaussianBlur(bright, (0, 0), max(radius / 2, 0.5))
    out = rgba.copy()
    out[..., :3] = 1 - (1 - rgba[..., :3]) * (1 - np.clip(glow * intensity, 0, 1))
    return out


def ripple(rgba, amplitude=4.0, wavelength=24.0, phase=0.0, direction="horizontal"):
    h, w = rgba.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if direction == "horizontal":
        mx, my = xx + amplitude * np.sin(2 * np.pi * yy / wavelength + phase), yy
    else:
        mx, my = xx, yy + amplitude * np.sin(2 * np.pi * xx / wavelength + phase)
    return cv2.remap(rgba, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


FILTERS: dict[str, tuple[Callable[..., np.ndarray], dict[str, Param], str]] = {
    "gaussian_blur": (gaussian_blur, {"radius": Param(4.0, 0, 500)}, "Gaussian blur, radius in px"),
    "box_blur": (box_blur, {"radius": Param(3, 1, 200)}, "Box blur"),
    "motion_blur": (motion_blur, {"distance": Param(20.0, 1, 500), "angle": Param(0.0, -360, 360)}, "Linear motion blur"),
    "lens_blur": (lens_blur, {"radius": Param(6.0, 1, 200), "highlight_boost": Param(0.0, 0, 4)}, "Disk/bokeh blur"),
    "unsharp_mask": (unsharp_mask, {"radius": Param(2.0, 0.1, 100), "amount": Param(0.8, 0, 5),
                                    "threshold": Param(0.0, 0, 255)}, "Sharpen via unsharp mask"),
    "high_pass": (high_pass, {"radius": Param(3.0, 0.1, 200)}, "High-pass (use with overlay/soft light)"),
    "add_noise": (add_noise, {"amount": Param(0.04, 0, 1), "monochrome": Param(True, kind="bool"),
                              "seed": Param(0, 0, 2**31), "grain_size": Param(1.0, 1, 8)}, "Film grain / noise"),
    "denoise": (denoise, {"strength": Param(6.0, 1, 30)}, "Non-local means denoise"),
    "median": (median, {"radius": Param(2, 1, 20)}, "Median filter"),
    "emboss": (emboss, {"strength": Param(1.0, 0, 10), "angle": Param(135.0, -360, 360)}, "Emboss"),
    "edge_detect": (edge_detect, {"low": Param(50, 0, 255), "high": Param(150, 0, 255)}, "Canny edges"),
    "vignette": (vignette, {"amount": Param(0.4, 0, 1), "radius": Param(0.75, 0, 2), "softness": Param(0.5, 0.01, 2)},
                 "Darken toward the edges"),
    "pixelate": (pixelate, {"cell": Param(8, 1, 512)}, "Pixelate"),
    "chromatic_aberration": (chromatic_aberration, {"shift": Param(2.0, 0, 50)}, "Lens chromatic aberration"),
    "gradient_blur": (gradient_blur, {"radius": Param(8.0, 0, 200), "focus_y": Param(0.5, 0, 1),
                                      "focus_band": Param(0.2, 0, 1), "falloff": Param(0.3, 0.01, 2),
                                      "angle": Param(0.0, -90, 90)}, "Tilt-shift / depth-of-field blur"),
    "bloom": (bloom, {"threshold": Param(0.75, 0, 1), "radius": Param(12.0, 0.5, 300),
                      "intensity": Param(0.6, 0, 3)}, "Glow around highlights"),
    "ripple": (ripple, {"amplitude": Param(4.0, 0, 200), "wavelength": Param(24.0, 1, 2000),
                        "phase": Param(0.0, -100, 100), "direction": Param("horizontal", kind="enum")}, "Sine ripple displacement"),
}


def validate_filter(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    if name not in FILTERS:
        raise ValidationError(f"Unknown filter '{name}'", details={"available": sorted(FILTERS)})
    _, spec, _ = FILTERS[name]
    params = dict(params or {})
    unknown = set(params) - set(spec)
    if unknown:
        raise ValidationError(f"Unknown parameters for filter {name}: {sorted(unknown)}",
                              details={"accepted": {k: v.default for k, v in spec.items()}})
    out = {}
    for k, p in spec.items():
        v = params.get(k, p.default)
        if p.kind == "number":
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValidationError(f"{name}.{k} must be a number")
            if (p.lo is not None and v < p.lo) or (p.hi is not None and v > p.hi):
                raise ValidationError(f"{name}.{k}={v} outside [{p.lo}, {p.hi}]")
        elif p.kind == "bool":
            v = bool(v)
        elif p.kind == "enum" and v not in ("horizontal", "vertical"):
            raise ValidationError(f"{name}.{k} must be 'horizontal' or 'vertical'")
        out[k] = v
    return out


def apply_filter(rgba: np.ndarray, name: str, params: dict[str, Any] | None) -> np.ndarray:
    clean = validate_filter(name, params)
    return np.clip(FILTERS[name][0](rgba.astype(np.float32), **clean), 0, 1).astype(np.float32)
