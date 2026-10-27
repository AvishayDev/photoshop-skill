"""Form lighting for painted shapes: height from silhouette, normals, diffuse/rim/specular light.

This is how a painter turns a flat silhouette into a rounded form: estimate a height field from the
distance to the outline, derive surface normals, and light them from the scene's key light.
"""

from __future__ import annotations

import cv2
import numpy as np

from .canvas import ColorLike, rgb


def light_vector(azimuth: float, elevation: float) -> np.ndarray:
    """Unit vector pointing TOWARD the light in image space (x right, y down, z toward the viewer).
    azimuth: where light comes from (0 right, 90 front/camera, 180 left, 270 behind); elevation in deg."""
    az, el = np.radians(azimuth), np.radians(elevation)
    v = np.array([np.cos(az) * np.cos(el), -np.sin(el), np.sin(az) * np.cos(el)], np.float32)
    return v / np.linalg.norm(v)


def height_from_mask(alpha: np.ndarray, radius: float | None = None, blur: float = 1.5) -> np.ndarray:
    """Rounded height field (0 at the outline, 1 on the ridge). ``radius``: px distance at which the form
    reaches full height (default: the shape's own max inner distance -> fully rounded)."""
    m = (alpha > 0.5).astype(np.uint8)
    if not m.any():
        return np.zeros_like(alpha, np.float32)
    d = cv2.distanceTransform(m, cv2.DIST_L2, 5).astype(np.float32)
    r = float(radius or d.max())
    t = np.clip(d / max(r, 1e-3), 0, 1)
    h = np.sqrt(np.clip(1 - (1 - t) ** 2, 0, 1))
    return cv2.GaussianBlur(h, (0, 0), blur) if blur > 0 else h


def normals(height: np.ndarray, depth: float = 30.0) -> np.ndarray:
    """Surface normals from a height field; ``depth`` = how many px of relief height 1.0 represents."""
    gx = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    n = np.stack([-gx * depth, -gy * depth, np.ones_like(height)], axis=-1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def shade(base: np.ndarray, alpha: np.ndarray, *, azimuth: float = 200.0, elevation: float = 40.0,
          key_color: ColorLike = "#fff3e0", ambient_color: ColorLike = "#9fb4d0", ambient: float = 0.35,
          wrap: float = 0.35, depth: float = 30.0, radius: float | None = None, height: np.ndarray | None = None,
          rim: float = 0.0, rim_color: ColorLike | None = None, specular: float = 0.0, shininess: float = 20.0,
          occlusion: float = 0.25) -> np.ndarray:
    """Light an (H, W, 3) base-colour image inside ``alpha`` as a rounded form. Returns (H, W, 3).

    ambient: fill-light level (sky/bounce, tinted ``ambient_color``); wrap: soft terminator for organic
    materials (fur, skin); rim: back/edge light strength; occlusion: darkening near the outline.
    """
    h = height if height is not None else height_from_mask(alpha, radius)
    n = normals(h, depth)
    L = light_vector(azimuth, elevation)
    ndl = (n @ L)
    diffuse = np.clip((ndl + wrap) / (1 + wrap), 0, 1)
    key = rgb(key_color)
    amb = rgb(ambient_color)
    light = amb * ambient + key * diffuse[..., None] * (1 - ambient * 0.5)
    out = base * light
    if occlusion > 0:
        out *= (1 - occlusion * (1 - np.clip(h * 1.6, 0, 1)))[..., None]
    if specular > 0:
        view = np.array([0, 0, 1], np.float32)
        half = (L + view) / np.linalg.norm(L + view)
        spec = np.clip(n @ half, 0, 1) ** shininess
        out += (key * specular) * spec[..., None]
    if rim > 0:
        edge = 1 - np.clip(n[..., 2], 0, 1)  # grazing normals near the outline
        side = np.clip(n[..., 0] * L[0] + n[..., 1] * L[1], 0, 1)  # facing the light's screen direction
        rim_amt = (edge ** 1.5) * (0.35 + 0.65 * side) * rim
        out += rgb(rim_color or key_color) * rim_amt[..., None]
    return np.clip(out, 0, 1)


def ground_bounce(alpha: np.ndarray, color: ColorLike, strength: float = 0.25, reach: float = 0.25) -> np.ndarray:
    """Weight map for bounced light from the ground on the lower part of a form (multiply by colour)."""
    ys = np.nonzero(alpha.max(axis=1) > 0.5)[0]
    if ys.size == 0:
        return np.zeros_like(alpha)
    top, bottom = ys.min(), ys.max()
    yy = np.arange(alpha.shape[0], dtype=np.float32)[:, None]
    t = np.clip((yy - (bottom - (bottom - top) * reach)) / max((bottom - top) * reach, 1), 0, 1)
    return (t * strength * alpha).astype(np.float32)
