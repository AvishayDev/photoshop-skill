"""Physically-motivated compositing helpers: shadows, reflections, light, color matching.

These generate *new* layer content from existing layers; the editor places
the results on separate, named layers so they remain adjustable.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..errors import ValidationError
from .color import luminance, parse_color, rgb_to_lab


def _bbox_alpha(alpha: np.ndarray, thr: float = 0.02):
    ys, xs = np.nonzero(alpha > thr)
    if len(xs) == 0:
        raise ValidationError("Layer has no visible pixels")
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def cast_shadow(alpha: np.ndarray, *, light_azimuth: float = 225.0, light_elevation: float = 35.0,
                ground_y: float | None = None, softness: float = 0.5, color: str = "#000000",
                opacity: float = 0.6, max_blur: float = 40.0) -> tuple[np.ndarray, int, int]:
    """Project a subject silhouette onto a flat ground plane.

    alpha: layer-local alpha (0..1). light_azimuth: direction the light comes FROM in degrees
    (image convention, y down: 0 = from the right, 90 = from the camera/front, 180 = from the left,
    270 = from behind the subject; 225 = upper-left behind, a common sun position).
    light_elevation: degrees above the horizon (low = long shadows). ground_y: layer-local y of
    the contact line (defaults to the silhouette's lowest pixel).
    Returns (rgba_u8, offset_x, offset_y) relative to the layer origin.
    """
    if not 3 <= light_elevation <= 89:
        raise ValidationError("light_elevation must be within 3..89 degrees")
    h, w = alpha.shape
    x0, y0, x1, y1 = _bbox_alpha(alpha)
    gy = float(ground_y) if ground_y is not None else float(y1)
    length = 1.0 / np.tan(np.deg2rad(light_elevation))  # shadow length per unit height
    az = np.deg2rad(light_azimuth)
    # shadow falls away from the light; vertical squash because the ground recedes
    dx = -np.cos(az) * length
    dy = -np.sin(az) * length * 0.35
    if abs(dy) < 0.03:
        dy = 0.03 if dy >= 0 else -0.03
    # each point at height t = gy - y maps to (x + dx*t, gy + dy*t)  -> affine shear/squash
    M = np.array([[1.0, -dx, dx * gy], [0.0, -dy, gy + dy * gy]], np.float64)
    height = gy - y0
    ext_x = int(abs(dx) * height) + 8
    ext_y = int(abs(dy) * height) + 8
    pad_l, pad_r = ext_x, ext_x
    pad_t, pad_b = ext_y, ext_y
    M2 = M.copy()
    M2[0, 2] += pad_l
    M2[1, 2] += pad_t
    W2, H2 = w + pad_l + pad_r, h + pad_t + pad_b
    proj = cv2.warpAffine(alpha.astype(np.float32), M2, (W2, H2), flags=cv2.INTER_LINEAR)
    # distance from contact line in the projected image controls blur (penumbra grows with distance)
    blur_lo = cv2.GaussianBlur(proj, (0, 0), 1.0 + softness * 2)
    blur_hi = cv2.GaussianBlur(proj, (0, 0), max(1.0, max_blur * softness))
    yy, xx = np.mgrid[0:H2, 0:W2].astype(np.float32)
    dist = np.hypot((xx - pad_l) - (x0 + x1) / 2, (yy - pad_t) - gy)
    t = np.clip(dist / max(height * max(length, 0.3), 1.0), 0, 1)
    shadow = blur_lo * (1 - t) + blur_hi * t
    shadow *= (1 - 0.6 * t)  # fades with distance
    c = parse_color(color)
    out = np.zeros((H2, W2, 4), np.uint8)
    out[..., :3] = c[:3]
    out[..., 3] = np.clip(shadow * opacity * 255, 0, 255).astype(np.uint8)
    return out, -pad_l, -pad_t


def contact_shadow(alpha: np.ndarray, *, ground_y: float | None = None, spread: float = 0.15,
                   blur: float = 6.0, opacity: float = 0.8, color: str = "#000000",
                   band: float = 0.06) -> tuple[np.ndarray, int, int]:
    """Dark, tight occlusion where the subject touches the ground."""
    h, w = alpha.shape
    x0, y0, x1, y1 = _bbox_alpha(alpha)
    gy = int(ground_y if ground_y is not None else y1)
    band_px = max(2, int((y1 - y0) * band))
    region = np.zeros_like(alpha, np.float32)
    lo = max(0, gy - band_px)
    region[lo:gy] = alpha[lo:gy]
    footprint = region.max(axis=0)  # columns that touch the ground
    pad = int(blur * 3 + (x1 - x0) * spread) + 4
    out_a = np.zeros((band_px * 4 + 2 * pad, w + 2 * pad), np.float32)
    cy = band_px + pad
    cols = np.flatnonzero(footprint > 0.05)
    if len(cols) == 0:
        raise ValidationError("No subject pixels near the ground line")
    for xc in cols:
        out_a[cy - band_px // 2: cy + band_px // 2 + 1, xc + pad] = footprint[xc]
    k = max(1, int((x1 - x0) * spread / 4))
    out_a = cv2.dilate(out_a, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, k + 1)))
    out_a = cv2.GaussianBlur(out_a, (0, 0), max(blur, 0.5))
    c = parse_color(color)
    out = np.zeros(out_a.shape + (4,), np.uint8)
    out[..., :3] = c[:3]
    out[..., 3] = np.clip(out_a * opacity * 255, 0, 255).astype(np.uint8)
    return out, -pad, gy - cy


def reflection(rgba: np.ndarray, *, axis_y: float | None = None, fade: float = 0.7, opacity: float = 0.55,
               blur: float = 2.0, ripple_amplitude: float = 3.0, ripple_wavelength: float = 18.0,
               squash: float = 1.0, tint: str | None = "#1d4e6b", tint_strength: float = 0.25,
               darken: float = 0.15, seed: int = 0) -> tuple[np.ndarray, int, int]:
    """Water / glossy-floor reflection of a layer mirrored about ``axis_y`` (layer-local).

    Real water reflections are darker than the subject (Fresnel), lose contrast,
    are broken up by waves, and fade with distance from the waterline.
    Returns (rgba_u8, offset_x, offset_y) relative to the layer origin.
    """
    h, w = rgba.shape[:2]
    alpha = rgba[..., 3].astype(np.float32) / 255
    _, _, _, y1 = _bbox_alpha(alpha)
    ay = int(round(axis_y if axis_y is not None else y1))
    src = rgba[:ay].astype(np.float32) / 255
    if src.shape[0] < 2:
        raise ValidationError("axis_y leaves nothing above the waterline to reflect")
    flipped = src[::-1].copy()
    if squash != 1.0:
        nh = max(2, int(flipped.shape[0] * squash))
        flipped = cv2.resize(flipped, (w, nh), interpolation=cv2.INTER_AREA)
    rh = flipped.shape[0]
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:rh, 0:w].astype(np.float32)
    depth = yy / max(rh, 1)
    if ripple_amplitude > 0:
        phase = rng.uniform(0, 2 * np.pi)
        jitter = cv2.GaussianBlur(rng.normal(0, 1, (rh, w)).astype(np.float32), (0, 0), 3) * 0.6
        disp = ripple_amplitude * (0.4 + depth) * (np.sin(2 * np.pi * yy / ripple_wavelength + phase) + jitter)
        flipped = cv2.remap(flipped, xx + disp, yy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if blur > 0:
        f = flipped.copy()
        f[..., :3] *= f[..., 3:4]
        f = cv2.GaussianBlur(f, (0, 0), blur / 2 + 0.01, sigmaY=blur + 0.01)
        a = f[..., 3:4]
        f[..., :3] = np.where(a > 1e-6, f[..., :3] / np.maximum(a, 1e-6), 0)
        flipped = f
    rgb = flipped[..., :3] * (1 - darken)
    if tint:
        c = np.array(parse_color(tint)[:3], np.float32) / 255
        rgb = rgb * (1 - tint_strength) + c * tint_strength
    fade_curve = np.clip(1 - depth / max(fade, 1e-3), 0, 1) ** 1.3
    out = np.zeros((rh, w, 4), np.float32)
    out[..., :3] = np.clip(rgb, 0, 1)
    out[..., 3] = flipped[..., 3] * fade_curve * opacity
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), 0, ay


def light_layer(width: int, height: int, kind: str, *, x: float = 0.5, y: float = 0.2, color: str = "#ffd9a0",
                intensity: float = 0.6, radius: float = 0.5, angle: float = 45.0, softness: float = 0.6,
                backdrop: np.ndarray | None = None, rays_length: float = 0.35, threshold: float = 0.65
                ) -> np.ndarray:
    """Create a light-effect layer (RGBA u8) for screen/soft-light blending.

    kinds: point (radial glow), directional (linear falloff from a side),
    god_rays (crepuscular rays streaming from (x, y) through bright gaps of the backdrop).
    x, y are normalized canvas coordinates.
    """
    c = np.array(parse_color(color)[:3], np.float32) / 255
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    cx, cy = x * width, y * height
    if kind == "point":
        r = radius * np.hypot(width, height) / 2
        d = np.hypot(xx - cx, yy - cy) / max(r, 1)
        a = np.clip(1 - d, 0, 1) ** (1 + 2 * softness)
    elif kind == "directional":
        rad = np.deg2rad(angle)
        proj = (xx - width / 2) * np.cos(rad) + (yy - height / 2) * np.sin(rad)
        half = (abs(width * np.cos(rad)) + abs(height * np.sin(rad))) / 2
        a = np.clip(1 - (proj + half) / max(2 * half, 1), 0, 1) ** (0.5 + softness * 2)
    elif kind == "god_rays":
        if backdrop is None:
            raise ValidationError("god_rays needs the rendered backdrop")
        lum = luminance(backdrop[..., :3]) * backdrop[..., 3]
        bright = np.clip((lum - threshold) / max(1 - threshold, 1e-3), 0, 1)
        a = _radial_blur(bright, cx, cy, rays_length)
        a = a / max(a.max(), 1e-6)
    else:
        raise ValidationError("light kind must be point, directional or god_rays")
    out = np.zeros((height, width, 4), np.float32)
    out[..., :3] = c
    out[..., 3] = np.clip(a * intensity, 0, 1)
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)


def _radial_blur(img: np.ndarray, cx: float, cy: float, length: float, samples: int = 48) -> np.ndarray:
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    acc = np.zeros_like(img)
    for i in range(samples):
        s = 1 - length * i / samples
        mx = cx + (xx - cx) * s
        my = cy + (yy - cy) * s
        acc += cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0) * (1 - i / samples)
    return acc / samples


def rim_light(rgba: np.ndarray, *, light_azimuth: float = 225.0, width: float = 4.0, color: str = "#ffe2b0",
              intensity: float = 0.7) -> np.ndarray:
    """Edge highlight on the side of a subject that faces the light (layer-local RGBA u8, same size)."""
    alpha = rgba[..., 3].astype(np.float32) / 255
    blurred = cv2.GaussianBlur(alpha, (0, 0), max(width, 0.5))
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    az = np.deg2rad(light_azimuth)
    lx, ly = np.cos(az), np.sin(az)
    # outward normal = -gradient; facing light when dot(normal, light_dir) > 0
    facing = np.clip(-(gx * lx + gy * ly) * 4, 0, 1)
    edge = np.clip(alpha - cv2.erode(alpha, np.ones((3, 3), np.uint8), iterations=max(1, int(width))), 0, 1)
    a = np.clip(facing * edge * 2, 0, 1) * intensity * alpha
    a = cv2.GaussianBlur(a, (0, 0), 0.8)
    c = parse_color(color)
    out = np.zeros(rgba.shape, np.uint8)
    out[..., :3] = c[:3]
    out[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    return out


def lab_stats(rgb: np.ndarray, weight: np.ndarray | None = None) -> tuple[list[float], list[float]]:
    lab = rgb_to_lab(np.clip(rgb, 0, 1)).reshape(-1, 3)
    if weight is not None:
        wv = weight.reshape(-1)
        sel = wv > 0.5
        if sel.sum() < 16:
            raise ValidationError("Too few pixels to measure color statistics")
        lab = lab[sel]
    return lab.mean(0).tolist(), lab.std(0).tolist()
