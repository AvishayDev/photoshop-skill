"""Brush engine: soft-dab strokes, directional hair/fur strokes and grass blades.

``stroke`` stamps round dabs along a path exactly like a Photoshop brush (size, hardness, spacing,
opacity, taper). ``fur`` and ``grass`` paint thousands of short anti-aliased strokes whose colour is
picked from the underlying painting, so they add texture without destroying patterns painted earlier.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from .canvas import ColorLike, rgb, to_u8
from .shapes import catmull_rom


def _dab(radius: float, hardness: float) -> np.ndarray:
    r = max(radius, 0.5)
    size = int(np.ceil(r)) * 2 + 3
    c = size / 2 - 0.5
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.hypot(xx - c, yy - c) / r
    hard = np.clip(hardness, 0, 0.99)
    a = np.clip((1 - d) / (1 - hard), 0, 1)
    return (a * a * (3 - 2 * a)).astype(np.float32)


def stroke(canvas: np.ndarray, points: Sequence[Sequence[float]], color: ColorLike, size: float = 10.0,
           hardness: float = 0.5, opacity: float = 1.0, spacing: float = 0.2, size_end: float | None = None,
           smooth: bool = True, flow: float = 1.0) -> np.ndarray:
    """Paint a brush stroke into an RGBA canvas in place (and return it). ``size`` = diameter in px;
    ``size_end`` tapers the stroke; ``flow`` is per-dab opacity (build-up), ``opacity`` caps the stroke."""
    pts = catmull_rom(points, closed=False, samples=10) if smooth and len(points) >= 3 \
        else np.asarray(points, np.float32)
    seg = np.hypot(*np.diff(pts, axis=0).T) if len(pts) > 1 else np.zeros(0)
    total = float(seg.sum())
    size_end = size if size_end is None else size_end
    step = max(0.5, min(size, size_end) * spacing)
    n = max(1, int(total / step) + 1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, total, n)
    xs = np.interp(t, cum, pts[:, 0]) if len(pts) > 1 else np.full(n, pts[0][0])
    ys = np.interp(t, cum, pts[:, 1]) if len(pts) > 1 else np.full(n, pts[0][1])
    sizes = np.linspace(size, size_end, n)
    H, W = canvas.shape[:2]
    col = rgb(color)
    cover = np.zeros((H, W), np.float32)
    for x, y, s in zip(xs, ys, sizes):
        d = _dab(s / 2, hardness) * flow
        k = d.shape[0]
        x0, y0 = int(round(x)) - k // 2, int(round(y)) - k // 2
        sx0, sy0 = max(0, -x0), max(0, -y0)
        ex, ey = min(k, W - x0), min(k, H - y0)
        if ex <= sx0 or ey <= sy0:
            continue
        reg = cover[y0 + sy0:y0 + ey, x0 + sx0:x0 + ex]
        np.maximum(reg, reg + d[sy0:ey, sx0:ex] * (1 - reg), out=reg)
    a = np.clip(cover, 0, 1) * opacity
    canvas[..., :3] = (col * a[..., None] + canvas[..., :3] * canvas[..., 3:4] * (1 - a[..., None])) / \
        np.maximum(a + canvas[..., 3] * (1 - a), 1e-6)[..., None]
    canvas[..., 3] = a + canvas[..., 3] * (1 - a)
    return canvas


def fur(painted: np.ndarray, mask: np.ndarray, angle: np.ndarray | float, *, density: float = 0.08,
        length: float = 9.0, width: float = 1.0, jitter: float = 0.18, angle_jitter: float = 12.0,
        lightness: float = 0.12, curl: float = 0.0, seed: int = 0, edge_hairs: float = 0.6) -> np.ndarray:
    """Overlay directional hair strokes on an RGB(A) painting inside ``mask``.

    Each stroke takes the colour under its root (so stripes/markings survive), randomly lightened or
    darkened by ``lightness``. ``angle`` (deg, image space, 0 = pointing right, 90 = down) may be a per-pixel
    field to make the fur flow along the body. ``edge_hairs`` lets strokes cross the outline (soft fur edge).
    Returns (rgb, alpha) as an RGBA float image.
    """
    H, W = mask.shape
    rng = np.random.default_rng(seed)
    base = to_u8(np.clip(painted[..., :3], 0, 1)).copy()
    alpha_u8 = to_u8(np.clip(mask, 0, 1)).copy()
    ys, xs = np.nonzero(mask > 0.5)
    if xs.size == 0:
        out = np.zeros((H, W, 4), np.float32)
        out[..., :3] = painted[..., :3]
        return out
    n = int(xs.size * density)
    idx = rng.integers(0, xs.size, n)
    px, py = xs[idx].astype(np.float32), ys[idx].astype(np.float32)
    ang = angle[py.astype(int), px.astype(int)] if isinstance(angle, np.ndarray) else np.full(n, float(angle))
    ang = np.radians(ang + rng.normal(0, angle_jitter, n))
    ln = length * rng.uniform(0.6, 1.3, n)
    ex, ey = px + np.cos(ang) * ln, py + np.sin(ang) * ln
    cols = base[py.astype(int), px.astype(int)].astype(np.float32)
    f = 1 + rng.uniform(-lightness, lightness, n) + rng.normal(0, jitter * 0.3, n)
    cols = np.clip(cols * f[:, None], 0, 255).astype(np.uint8)
    thick = max(1, int(round(width)))
    for i in range(n):
        p0 = (int(px[i] * 16), int(py[i] * 16))
        if curl:
            mx = (px[i] + ex[i]) / 2 + np.cos(ang[i] + np.pi / 2) * curl * ln[i] * 0.3
            my = (py[i] + ey[i]) / 2 + np.sin(ang[i] + np.pi / 2) * curl * ln[i] * 0.3
            pts = np.array([[px[i], py[i]], [mx, my], [ex[i], ey[i]]]) * 16
            cv2.polylines(base, [pts.astype(np.int32)], False, cols[i].tolist(), thick, cv2.LINE_AA, 4)
        else:
            cv2.line(base, p0, (int(ex[i] * 16), int(ey[i] * 16)), cols[i].tolist(), thick, cv2.LINE_AA, 4)
    out = np.zeros((H, W, 4), np.float32)
    out[..., :3] = base.astype(np.float32) / 255
    alpha = mask.astype(np.float32)
    if edge_hairs > 0:
        # hairs that cross the outline: draw stroke coverage only, near the edge
        edge = (cv2.dilate((mask > 0.5).astype(np.uint8), np.ones((3, 3), np.uint8)) -
                cv2.erode((mask > 0.5).astype(np.uint8), np.ones((3, 3), np.uint8))) > 0
        ey_, ex_ = np.nonzero(edge)
        m = int(ex_.size * edge_hairs)
        if m:
            j = rng.integers(0, ex_.size, m)
            a2 = np.radians((angle[ey_[j], ex_[j]] if isinstance(angle, np.ndarray) else np.full(m, float(angle)))
                            + rng.normal(0, angle_jitter * 1.5, m))
            l2 = length * rng.uniform(0.3, 0.9, m)
            for i in range(m):
                x0, y0 = ex_[j[i]], ey_[j[i]]
                cv2.line(alpha_u8, (int(x0 * 16), int(y0 * 16)),
                         (int((x0 + np.cos(a2[i]) * l2[i]) * 16), int((y0 + np.sin(a2[i]) * l2[i]) * 16)),
                         200, 1, cv2.LINE_AA, 4)
            alpha = np.maximum(alpha, alpha_u8.astype(np.float32) / 255)
            # hairs outside the body need colour: spread nearby colours outward
            grown = cv2.dilate(out[..., :3], np.ones((5, 5), np.uint8))
            outside = (mask < 0.5)[..., None]
            out[..., :3] = np.where(outside, grown, out[..., :3])
    out[..., 3] = alpha
    return out


def grass(width: int, height: int, top: float, bottom: float, *, density: float = 0.004,
          length: tuple[float, float] = (20, 60), colors: Sequence[ColorLike] = ("#3d5a1e", "#6b8f2a", "#a3b44c"),
          lean: float = 15.0, light_azimuth: float = 180.0, thickness: float = 1.6, seed: int = 0,
          perspective: bool = True) -> np.ndarray:
    """Grass/undergrowth blades rooted between rows ``top`` and ``bottom``; blades shrink with distance
    (toward ``top``) when ``perspective`` is set. Returns RGBA."""
    rng = np.random.default_rng(seed)
    img = np.zeros((height, width, 3), np.uint8)
    cov = np.zeros((height, width), np.uint8)
    area = width * max(bottom - top, 1)
    n = int(area * density)
    roots_y = np.sort(rng.uniform(top, bottom, n))  # far (small) blades first
    roots_x = rng.uniform(-10, width + 10, n)
    cols = np.stack([rgb(c) for c in colors]) * 255
    light_side = np.cos(np.radians(light_azimuth))
    for x, y in zip(roots_x, roots_y):
        depth = (y - top) / max(bottom - top, 1) if perspective else 1.0
        s = 0.25 + 0.75 * depth
        ln = rng.uniform(*length) * s
        a = np.radians(-90 + rng.normal(0, lean))
        bend = rng.normal(0, 0.35)
        pts = []
        for t in np.linspace(0, 1, 5):
            pts.append([x + np.cos(a) * ln * t + bend * ln * t * t, y + np.sin(a) * ln * t])
        lit = 0.5 + 0.5 * np.sign(np.cos(a) + bend) * light_side
        ci = rng.random() * (len(cols) - 1) * (0.5 + 0.5 * lit) + 0.4 * depth
        c = cols[min(int(ci), len(cols) - 1)] * (0.55 + 0.45 * depth) * rng.uniform(0.85, 1.1)
        pts16 = (np.array(pts) * 16).astype(np.int32)
        th = max(1, int(round(thickness * s)))
        cv2.polylines(img, [pts16], False, np.clip(c, 0, 255).tolist(), th, cv2.LINE_AA, 4)
        cv2.polylines(cov, [pts16], False, 255, th, cv2.LINE_AA, 4)
    out = np.zeros((height, width, 4), np.float32)
    out[..., :3] = img.astype(np.float32) / 255
    out[..., 3] = cov.astype(np.float32) / 255
    a = out[..., 3:4]
    out[..., :3] = np.where(a > 0, out[..., :3] / np.maximum(a, 1e-3), 0)
    return np.clip(out, 0, 1)
