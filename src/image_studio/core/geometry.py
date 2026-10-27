"""Geometric transforms: affine/perspective warps, resampling, flips."""

from __future__ import annotations

import cv2
import numpy as np

from ..errors import ValidationError

INTERP = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR, "cubic": cv2.INTER_CUBIC,
          "lanczos": cv2.INTER_LANCZOS4, "area": cv2.INTER_AREA}


def interp_flag(name: str) -> int:
    try:
        return INTERP[name]
    except KeyError:
        raise ValidationError(f"interpolation must be one of {sorted(INTERP)}") from None


def translation(tx: float, ty: float) -> np.ndarray:
    return np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], np.float64)


def scale_rotate_about(cx: float, cy: float, sx: float, sy: float, angle_deg: float,
                       shear_x: float = 0.0, shear_y: float = 0.0) -> np.ndarray:
    a = np.deg2rad(angle_deg)
    rot = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    sc = np.diag([sx, sy, 1.0])
    sh = np.array([[1, np.tan(np.deg2rad(shear_x)), 0], [np.tan(np.deg2rad(shear_y)), 1, 0], [0, 0, 1]])
    return translation(cx, cy) @ rot @ sh @ sc @ translation(-cx, -cy)


def perspective_from_corners(w: int, h: int, corners: list[list[float]]) -> np.ndarray:
    """Matrix mapping the base rect (0,0)-(w,h) to 4 target corners: TL, TR, BR, BL (document coords)."""
    if len(corners) != 4:
        raise ValidationError("perspective needs exactly 4 corners: top-left, top-right, bottom-right, bottom-left")
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    dst = np.array(corners, np.float32)
    return cv2.getPerspectiveTransform(src, dst).astype(np.float64)


def warp(pixels: np.ndarray, matrix: np.ndarray, interpolation: str = "cubic",
         max_pixels: int = 120_000_000) -> tuple[np.ndarray, int, int]:
    """Warp ``pixels`` by ``matrix`` (base -> doc). Returns (out, x, y) of the tight output bounds."""
    h, w = pixels.shape[:2]
    corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], np.float64).T
    mapped = matrix @ corners
    if np.any(np.abs(mapped[2]) < 1e-9):
        raise ValidationError("Degenerate perspective transform")
    mapped = mapped[:2] / mapped[2]
    x0, y0 = np.floor(mapped.min(axis=1)).astype(int)
    x1, y1 = np.ceil(mapped.max(axis=1)).astype(int)
    ow, oh = int(x1 - x0), int(y1 - y0)
    if ow < 1 or oh < 1:
        raise ValidationError("Transform collapses the layer to zero size")
    if ow * oh > max_pixels:
        raise ValidationError("Transform result would be too large")
    # OpenCV samples at pixel centers; our matrices use pixel-edge coordinates (a pixel covers [c, c+1]).
    m = translation(-0.5, -0.5) @ translation(-x0, -y0) @ matrix @ translation(0.5, 0.5)
    flag = interp_flag(interpolation)
    src = pixels
    if pixels.ndim == 3 and pixels.shape[2] == 4:
        # premultiply to avoid dark/colored fringes at transparent edges
        f = pixels.astype(np.float32) / 255
        f[..., :3] *= f[..., 3:4]
        src = f
    if np.allclose(m[2], [0, 0, 1]):
        out = cv2.warpAffine(src, m[:2], (ow, oh), flags=flag, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    else:
        out = cv2.warpPerspective(src, m, (ow, oh), flags=flag, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    if src is not pixels:
        out = np.clip(out, 0, 1)
        a = out[..., 3:4]
        out[..., :3] = np.where(a > 1e-6, out[..., :3] / np.maximum(a, 1e-6), 0)
        out = np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)
    return out, int(x0), int(y0)


def resize(pixels: np.ndarray, width: int, height: int, interpolation: str = "lanczos") -> np.ndarray:
    if width < 1 or height < 1:
        raise ValidationError("Target size must be at least 1x1")
    flag = interp_flag(interpolation)
    if width < pixels.shape[1] and height < pixels.shape[0] and interpolation == "lanczos":
        flag = cv2.INTER_AREA  # better for downscaling
    if pixels.ndim == 3 and pixels.shape[2] == 4:
        f = pixels.astype(np.float32) / 255
        f[..., :3] *= f[..., 3:4]
        r = np.clip(cv2.resize(f, (width, height), interpolation=flag), 0, 1)
        a = r[..., 3:4]
        r[..., :3] = np.where(a > 1e-6, r[..., :3] / np.maximum(a, 1e-6), 0)
        return np.clip(r * 255 + 0.5, 0, 255).astype(np.uint8)
    return cv2.resize(pixels, (width, height), interpolation=flag)
