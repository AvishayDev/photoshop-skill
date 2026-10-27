"""Anti-aliased shape masks: smooth paths, ellipses, tapered capsules and organic blobs."""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

_SHIFT = 4  # sub-pixel precision for OpenCV drawing (1/16 px)


def _pts(points) -> np.ndarray:
    return np.round(np.asarray(points, np.float64) * (1 << _SHIFT)).astype(np.int32)


def catmull_rom(points: Sequence[Sequence[float]], closed: bool = True, samples: int = 12) -> np.ndarray:
    """Smooth curve through control points (centripetal-ish uniform Catmull-Rom)."""
    p = np.asarray(points, np.float32)
    if len(p) < 3:
        return p
    if closed:
        p = np.vstack([p[-1], p, p[0], p[1]])
    else:
        p = np.vstack([p[0], p, p[-1]])
    out = []
    t = np.linspace(0, 1, samples, endpoint=False, dtype=np.float32)[:, None]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed:
        out.append(p[-2][None])
    return np.vstack(out)


def polygon(width: int, height: int, points, feather: float = 0.0, smooth: bool = False) -> np.ndarray:
    """Filled polygon mask (optionally smoothed through its points with Catmull-Rom)."""
    pts = catmull_rom(points, closed=True) if smooth else np.asarray(points, np.float32)
    m = np.zeros((height, width), np.uint8)
    cv2.fillPoly(m, [_pts(pts)], 255, cv2.LINE_AA, _SHIFT)
    out = m.astype(np.float32) / 255
    return cv2.GaussianBlur(out, (0, 0), feather) if feather > 0 else out


def ellipse(width: int, height: int, cx: float, cy: float, rx: float, ry: float, angle: float = 0.0,
            feather: float = 0.0) -> np.ndarray:
    m = np.zeros((height, width), np.uint8)
    cv2.ellipse(m, (int(round(cx * 16)), int(round(cy * 16))),
                (max(1, int(round(rx * 16))), max(1, int(round(ry * 16)))), angle, 0, 360, 255, -1,
                cv2.LINE_AA, _SHIFT)
    out = m.astype(np.float32) / 255
    return cv2.GaussianBlur(out, (0, 0), feather) if feather > 0 else out


def capsule(width: int, height: int, p0, p1, r0: float, r1: float | None = None,
            feather: float = 0.0) -> np.ndarray:
    """Tapered capsule from p0 (radius r0) to p1 (radius r1): limbs, tails, necks, trunks."""
    r1 = r0 if r1 is None else r1
    p0, p1 = np.asarray(p0, np.float32), np.asarray(p1, np.float32)
    d = p1 - p0
    length = float(np.hypot(*d))
    m = np.zeros((height, width), np.uint8)
    if length > 1e-3:
        n = np.array([-d[1], d[0]], np.float32) / length
        quad = [p0 + n * r0, p1 + n * r1, p1 - n * r1, p0 - n * r0]
        cv2.fillPoly(m, [_pts(quad)], 255, cv2.LINE_AA, _SHIFT)
    for p, r in ((p0, r0), (p1, r1)):
        cv2.circle(m, tuple(int(round(v * 16)) for v in p), max(1, int(round(r * 16))), 255, -1, cv2.LINE_AA,
                   _SHIFT)
    out = m.astype(np.float32) / 255
    return cv2.GaussianBlur(out, (0, 0), feather) if feather > 0 else out


def bent_capsule(width: int, height: int, points, radii, feather: float = 0.0) -> np.ndarray:
    """Chain of tapered capsules through a polyline (legs with joints, curved necks, tails)."""
    out = np.zeros((height, width), np.float32)
    pts = catmull_rom(points, closed=False, samples=8) if len(points) >= 3 else np.asarray(points, np.float32)
    rs = np.interp(np.linspace(0, 1, len(pts)), np.linspace(0, 1, len(radii)), radii)
    for i in range(len(pts) - 1):
        out = np.maximum(out, capsule(width, height, pts[i], pts[i + 1], rs[i], rs[i + 1]))
    return cv2.GaussianBlur(out, (0, 0), feather) if feather > 0 else out


def blob(width: int, height: int, cx: float, cy: float, r: float, irregularity: float = 0.25,
         seed: int = 0, n: int = 18, squash: float = 1.0, feather: float = 0.0) -> np.ndarray:
    """Organic closed blob (foliage clumps, rocks, clouds, spots)."""
    rng = np.random.default_rng(seed)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + rng.uniform(0, 2 * np.pi)
    rad = r * (1 + irregularity * (rng.random(n) * 2 - 1))
    pts = np.stack([cx + np.cos(ang) * rad, cy + np.sin(ang) * rad * squash], axis=1)
    return polygon(width, height, pts, feather=feather, smooth=True)


def polyline(width: int, height: int, points, thickness: float, feather: float = 0.0) -> np.ndarray:
    m = np.zeros((height, width), np.uint8)
    cv2.polylines(m, [_pts(points)], False, 255, max(1, int(round(thickness))), cv2.LINE_AA, _SHIFT)
    out = m.astype(np.float32) / 255
    return cv2.GaussianBlur(out, (0, 0), feather) if feather > 0 else out


def axis_coords(width: int, height: int, p0, p1) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel (u, v) in the frame of segment p0->p1: u along the axis (0 at p0, 1 at p1), v signed
    perpendicular distance in px (positive to the right of the direction of travel, i.e. 'below' for a
    left-to-right axis)."""
    p0, p1 = np.asarray(p0, np.float32), np.asarray(p1, np.float32)
    d = p1 - p0
    L = max(float(np.hypot(*d)), 1e-6)
    ux, uy = d / L
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    rx, ry = xs - p0[0], ys - p0[1]
    u = (rx * ux + ry * uy) / L
    v = -rx * uy + ry * ux
    return u, v
