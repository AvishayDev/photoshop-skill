"""Selection and mask construction (document- or layer-sized float masks in 0..1)."""

from __future__ import annotations

import cv2
import numpy as np

from ..errors import ValidationError
from .color import parse_color

MODES = ("replace", "add", "subtract", "intersect")


def shape_mask(width: int, height: int, shape: str, *, x: float = 0, y: float = 0, w: float = 0, h: float = 0,
               points: list[list[float]] | None = None, antialias: bool = True) -> np.ndarray:
    m = np.zeros((height, width), np.float32)
    line = cv2.LINE_AA if antialias else cv2.LINE_8
    if shape == "all":
        m[:] = 1
    elif shape == "none":
        pass
    elif shape == "rectangle":
        if w <= 0 or h <= 0:
            raise ValidationError("rectangle selection needs positive width and height")
        x0, y0 = int(round(x)), int(round(y))
        m[max(0, y0):max(0, int(round(y + h))), max(0, x0):max(0, int(round(x + w)))] = 1
    elif shape == "ellipse":
        if w <= 0 or h <= 0:
            raise ValidationError("ellipse selection needs positive width and height")
        ss = 4
        big = np.zeros((height * ss, width * ss), np.uint8) if antialias else None
        if antialias:
            cv2.ellipse(big, (int((x + w / 2) * ss), int((y + h / 2) * ss)), (int(w / 2 * ss), int(h / 2 * ss)),
                        0, 0, 360, 255, -1)
            m = cv2.resize(big, (width, height), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        else:
            cv2.ellipse(m, (int(x + w / 2), int(y + h / 2)), (int(w / 2), int(h / 2)), 0, 0, 360, 1.0, -1)
    elif shape == "polygon":
        if not points or len(points) < 3:
            raise ValidationError("polygon selection needs at least 3 points")
        pts = np.array([[p[0] * 16, p[1] * 16] for p in points], np.int32)
        cv2.fillPoly(m, [pts], 1.0, lineType=line, shift=4)
    else:
        raise ValidationError(f"Unknown selection shape '{shape}'",
                              hint="Use all, none, rectangle, ellipse or polygon")
    return np.clip(m, 0, 1)


def combine(existing: np.ndarray | None, new: np.ndarray, mode: str) -> np.ndarray:
    if mode not in MODES:
        raise ValidationError(f"mode must be one of {MODES}")
    if existing is None or mode == "replace":
        return new
    if mode == "add":
        return np.maximum(existing, new)
    if mode == "subtract":
        return np.clip(existing - new, 0, 1)
    return np.minimum(existing, new)


def feather(mask: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return mask
    return np.clip(cv2.GaussianBlur(mask, (0, 0), radius / 2.0), 0, 1)


def grow(mask: np.ndarray, pixels: int) -> np.ndarray:
    if pixels == 0:
        return mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * abs(pixels) + 1, 2 * abs(pixels) + 1))
    return cv2.dilate(mask, k) if pixels > 0 else cv2.erode(mask, k)


def color_mask(rgba: np.ndarray, color, tolerance: float = 32.0, *, contiguous_from: tuple[int, int] | None = None,
               soft: bool = True) -> np.ndarray:
    """Select pixels close to ``color`` (Euclidean RGB distance, 0..441). Optionally only the region
    connected to ``contiguous_from`` (a fuzzy-select / magic-wand)."""
    target = np.array(parse_color(color)[:3], np.float32) / 255
    dist = np.linalg.norm(rgba[..., :3] - target, axis=-1) * 255
    tol = max(float(tolerance), 0.5)
    m = np.clip(1 - (dist - tol * 0.75) / (tol * 0.25), 0, 1) if soft else (dist <= tol).astype(np.float32)
    m *= (rgba[..., 3] > 0.01)
    if contiguous_from is not None:
        x, y = contiguous_from
        if not (0 <= x < m.shape[1] and 0 <= y < m.shape[0]):
            raise ValidationError("Seed point lies outside the layer")
        binary = (m > 0.01).astype(np.uint8)
        n, labels = cv2.connectedComponents(binary, connectivity=8)
        lab = labels[y, x]
        if lab == 0:
            return np.zeros_like(m)
        m = m * (labels == lab)
    return m.astype(np.float32)


def linear_gradient_mask(width: int, height: int, start: tuple[float, float], end: tuple[float, float],
                         reverse: bool = False) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dx, dy = end[0] - start[0], end[1] - start[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-6:
        raise ValidationError("Gradient start and end must differ")
    t = np.clip(((xx - start[0]) * dx + (yy - start[1]) * dy) / L2, 0, 1)
    t = 1 - t if not reverse else t
    return t.astype(np.float32)


def radial_gradient_mask(width: int, height: int, center: tuple[float, float], radius: float,
                         inner: float = 0.0) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    d = np.hypot(xx - center[0], yy - center[1])
    r0 = radius * inner
    return np.clip(1 - (d - r0) / max(radius - r0, 1e-3), 0, 1).astype(np.float32)


def brush_strokes_mask(width: int, height: int, strokes: list[list[list[float]]], size: float,
                       hardness: float = 0.5, spacing: float = 0.15) -> np.ndarray:
    """Rasterize brush strokes (lists of [x, y] points) into a soft mask."""
    m = np.zeros((height, width), np.float32)
    dab = brush_dab(size, hardness)
    r = dab.shape[0] // 2
    for pt, _ in dab_positions(strokes, size, spacing):
        stamp(m, dab, pt[0], pt[1], r)
    return np.clip(m, 0, 1)


def brush_dab(size: float, hardness: float) -> np.ndarray:
    if size < 1:
        raise ValidationError("brush size must be >= 1 px")
    if not 0 <= hardness <= 1:
        raise ValidationError("hardness must be within 0..1")
    r = max(1, int(np.ceil(size / 2)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(np.float32)
    d = np.hypot(xx, yy) / (size / 2)
    h = min(hardness, 0.999)
    dab = np.clip((1 - d) / (1 - h), 0, 1)
    return (dab * dab * (3 - 2 * dab)).astype(np.float32)


def dab_positions(strokes: list[list[list[float]]], size: float, spacing: float = 0.15):
    step = max(1.0, size * spacing)
    for stroke in strokes:
        if not stroke:
            continue
        pts = [np.array(p[:2], np.float64) for p in stroke]
        yield pts[0], 0
        carry = 0.0
        for a, b in zip(pts, pts[1:]):
            seg = b - a
            L = float(np.hypot(*seg))
            t = step - carry
            while t <= L:
                yield a + seg * (t / L), 1
                t += step
            carry = L - (t - step)


def stamp(target: np.ndarray, dab: np.ndarray, cx: float, cy: float, r: int) -> None:
    H, W = target.shape[:2]
    x0, y0 = int(round(cx)) - r, int(round(cy)) - r
    x1, y1 = x0 + dab.shape[1], y0 + dab.shape[0]
    tx0, ty0, tx1, ty1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if tx1 <= tx0 or ty1 <= ty0:
        return
    sub = dab[ty0 - y0:ty1 - y0, tx0 - x0:tx1 - x0]
    np.maximum(target[ty0:ty1, tx0:tx1], sub, out=target[ty0:ty1, tx0:tx1])
