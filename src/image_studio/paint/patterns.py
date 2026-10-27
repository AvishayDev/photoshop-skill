"""Pattern generators learned from nature: stripes, spots/rosettes, eyespots, scales, bark.

Every generator is parametric so the parameters can be *measured* on reference photos
(:mod:`image_studio.patterns.learn`) and stored in the pattern library for reuse.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from .canvas import ColorLike, ramp, rgb, smoothstep
from .noise import fbm, value_noise, worley


def stripes(width: int, height: int, *, period: float = 40.0, thickness: float = 0.35, angle: float = 0.0,
            u: np.ndarray | None = None, warp: float = 0.35, warp_period: float | None = None,
            breakup: float = 0.35, taper: float = 0.6, fork: float = 0.25, edge: float = 1.2,
            seed: int = 0) -> np.ndarray:
    """Organic stripe mask in 0..1 (tiger, zebra, tabby, bark bands).

    period: stripe spacing in px; thickness: dark fraction of each period; angle: direction ACROSS the stripes
    (0 = stripes are vertical bands repeating left->right). ``u`` overrides the coordinate across the
    stripes (e.g. distance along a body's spine) so stripes wrap around forms. warp: waviness as a fraction
    of the period; breakup: how often stripes end/break; taper: thickness variation along a stripe (pointed
    ends); fork: tendency to split into Y-shapes; edge: edge softness in px.
    """
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    a = np.radians(angle)
    if u is None:
        u = xs * np.cos(a) + ys * np.sin(a)
    wp = warp_period or period * 2.5
    u = u + (fbm(width, height, wp, 3, seed=seed) - 0.5) * 2 * warp * period
    phase = u / period
    cell = np.floor(phase)
    v = phase - cell  # 0..1 across one period
    # thickness varies along the stripe -> tapered, pointed ends
    n_th = fbm(width, height, period * 1.6, 3, seed=seed + 5)
    th = thickness * (1 - taper + taper * 2 * n_th)
    # forks: a second, thinner band appears where noise is high
    n_fork = fbm(width, height, period * 2.2, 2, seed=seed + 9)
    dist = np.abs(v - 0.5)  # 0 at the stripe centre
    fork_gap = np.where(n_fork > 1 - fork, 0.18 * th * (n_fork - (1 - fork)) / max(fork, 1e-3), 0)
    dist = np.where(fork_gap > 0, np.abs(dist - fork_gap), dist)
    px_per_v = period
    m = smoothstep(-edge, edge, (th / 2 - dist) * px_per_v)
    # break-up: stripes end where low-frequency noise (varying per stripe) is low
    if breakup > 0:
        n_b = fbm(width, height, period * 3.0, 3, seed=seed + 13)
        shift = (np.sin(cell * 12.9898) * 43758.5453) % 1.0  # per-stripe offset
        n_b = (n_b + shift * 0.5) % 1.0
        m *= smoothstep(breakup - 0.08, breakup + 0.08, n_b)
    return m.astype(np.float32)


def spots(width: int, height: int, *, size: float = 18.0, spacing: float | None = None, rosette: bool = False,
          irregularity: float = 0.35, seed: int = 0) -> np.ndarray:
    """Spot mask (cheetah/dalmatian spots, or leopard/jaguar rosettes when ``rosette``)."""
    spacing = spacing or size * 2.6
    dist, labels, pts = worley(width, height, spacing, seed=seed)
    rng = np.random.default_rng(seed + 1)
    out = np.zeros((height, width), np.float32)
    wob = (fbm(width, height, size * 1.2, 3, seed=seed + 2) - 0.5) * 2 * irregularity
    d_px = dist * spacing
    if not rosette:
        r = size / 2 * (1 + wob)
        out = smoothstep(-1, 1, r - d_px)
    else:
        ring_r = size * 0.55 * (1 + wob * 0.6)
        ring = smoothstep(-1, 1, size * 0.22 - np.abs(d_px - ring_r))
        # break the ring into 3-5 segments
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        lab = labels.ravel() - 1
        lab = np.clip(lab, 0, None)
        ang = np.arctan2(ys.ravel() - pts[np.minimum(lab, len(pts) - 1), 1],
                         xs.ravel() - pts[np.minimum(lab, len(pts) - 1), 0]).reshape(height, width)
        k = rng.integers(3, 6, len(pts) + 1)[np.minimum(labels, len(pts))]
        gaps = (np.cos(ang * k + labels * 1.7) > -0.55).astype(np.float32)
        out = ring * cv2.GaussianBlur(gaps, (0, 0), 1.0)
    keep = rng.random(len(pts) + 2)[np.minimum(labels, len(pts) + 1)] < 0.92
    return (out * keep).astype(np.float32)


def eyespot(radius: float, colors: Sequence[ColorLike] = ("#0b1d4a", "#1b6fa8", "#1f9e7a", "#c9a227", "#6e8a2a"),
            rings: Sequence[float] = (0.32, 0.5, 0.68, 0.84, 1.0), squash: float = 1.25,
            offset: float = 0.12) -> np.ndarray:
    """Concentric ocellus (peacock train feather 'eye'). Returns a small RGBA patch, centre-weighted:
    dark heart -> blue -> turquoise -> bronze -> green fringe (inner to outer by default)."""
    r = max(float(radius), 2.0)
    size = int(np.ceil(r * 2 * squash)) + 4
    c = size / 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    out = np.zeros((size, size, 4), np.float32)
    for i in range(len(colors) - 1, -1, -1):
        rr = r * rings[i]
        # inner rings sit slightly toward the feather base (offset) - like real ocelli
        cy = c + offset * r * (1 - rings[i])
        d = np.hypot((xx - c) / rr, (yy - cy) / (rr * squash))
        m = smoothstep(1.0 + 1.2 / rr, 1.0 - 1.2 / rr, d)
        col = rgb(colors[i])
        out[..., :3] = out[..., :3] * (1 - m[..., None]) + col * m[..., None]
        out[..., 3] = np.maximum(out[..., 3], m)
    return out


def scales(width: int, height: int, *, size: float = 16.0, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Overlapping scale/feather-tip pattern. Returns (height-like shading 0..1, edge lines 0..1)."""
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    row = np.floor(ys / (size * 0.6))
    xo = xs + (row % 2) * size / 2
    cx = (np.floor(xo / size) + 0.5) * size
    cy = (row + 1) * size * 0.6
    d = np.hypot(xo - cx, (ys - cy) * 1.1) / (size * 0.62)
    shade_ = np.clip(1 - d, 0, 1)
    edges = smoothstep(0.85, 1.0, d) * (1 - smoothstep(1.0, 1.15, d))
    jitter = value_noise(width, height, size, seed) * 0.25
    return np.clip(shade_ + jitter, 0, 1), edges


def bark(width: int, height: int, *, period: float = 14.0, seed: int = 0) -> np.ndarray:
    """Vertical fissured bark field 0..1 (dark = fissures)."""
    n = fbm(max(2, width // 3), height, period, 4, seed=seed)
    n = cv2.resize(n, (width, height), interpolation=cv2.INTER_CUBIC)
    ridges = 1 - np.abs(n * 2 - 1)
    fine = fbm(width, height, period / 3, 3, seed=seed + 1)
    return np.clip(ridges * 0.75 + fine * 0.25, 0, 1)


def colorize(mask: np.ndarray, base: np.ndarray, color: ColorLike, strength: float = 1.0) -> np.ndarray:
    """Paint ``color`` into an (H, W, 3) image where ``mask`` is set."""
    return base * (1 - mask[..., None] * strength) + rgb(color) * (mask[..., None] * strength)


def palette_field(field: np.ndarray, colors: Sequence[ColorLike]) -> np.ndarray:
    return ramp(field, colors)
