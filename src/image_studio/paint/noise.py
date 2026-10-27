"""Seeded noise fields: value-noise fBm, domain warping, Worley cells and perspective texture mapping."""

from __future__ import annotations

import cv2
import numpy as np


def value_noise(width: int, height: int, period: float, seed: int = 0) -> np.ndarray:
    """Smooth random field with features about ``period`` pixels wide, in 0..1."""
    rng = np.random.default_rng(seed)
    period = max(float(period), 1.0)
    gw, gh = int(width / period) + 4, int(height / period) + 4
    grid = rng.random((gh, gw)).astype(np.float32)
    big = cv2.resize(grid, (int(gw * period), int(gh * period)), interpolation=cv2.INTER_CUBIC)
    ox = int(rng.integers(0, max(1, big.shape[1] - width)))
    oy = int(rng.integers(0, max(1, big.shape[0] - height)))
    return np.clip(big[oy:oy + height, ox:ox + width], 0, 1)


def fbm(width: int, height: int, period: float = 64.0, octaves: int = 5, gain: float = 0.5,
        lacunarity: float = 2.0, seed: int = 0, normalize: bool = True) -> np.ndarray:
    """Fractal Brownian motion: octaves of value noise. ``period`` is the largest feature size in px."""
    out = np.zeros((height, width), np.float32)
    amp, total, p = 1.0, 0.0, float(period)
    for o in range(octaves):
        if p < 1.5:
            break
        out += amp * value_noise(width, height, p, seed * 7919 + o * 104729)
        total += amp
        amp *= gain
        p /= lacunarity
    out /= max(total, 1e-6)
    if normalize:
        lo, hi = np.percentile(out, 0.5), np.percentile(out, 99.5)
        out = np.clip((out - lo) / max(hi - lo, 1e-6), 0, 1)
    return out


def ridged(width: int, height: int, period: float = 64.0, octaves: int = 5, seed: int = 0) -> np.ndarray:
    """Sharp-crested noise (mountain ridges, cracks, veins)."""
    n = fbm(width, height, period, octaves, seed=seed)
    return 1 - np.abs(n * 2 - 1)


def warp(img: np.ndarray, strength: float, period: float, seed: int = 0) -> np.ndarray:
    """Domain-warp an image/field: displace pixels by smooth noise (organic irregularity)."""
    h, w = img.shape[:2]
    dx = (fbm(w, h, period, 3, seed=seed + 11) - 0.5) * 2 * strength
    dy = (fbm(w, h, period, 3, seed=seed + 23) - 0.5) * 2 * strength
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(img, xs + dx, ys + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def worley(width: int, height: int, cell: float, seed: int = 0, jitter: float = 0.9
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cellular noise. Returns (F1 distance / cell, nearest-cell label, seed points (N, 2))."""
    rng = np.random.default_rng(seed)
    nx, ny = int(width / cell) + 2, int(height / cell) + 2
    gx, gy = np.meshgrid(np.arange(nx), np.arange(ny))
    pts = np.stack([(gx.ravel() + 0.5 + (rng.random(gx.size) - 0.5) * jitter) * cell - cell / 2,
                    (gy.ravel() + 0.5 + (rng.random(gy.size) - 0.5) * jitter) * cell - cell / 2], axis=1)
    seeds = np.full((height, width), 255, np.uint8)
    inside = (pts[:, 0] >= 0) & (pts[:, 0] < width) & (pts[:, 1] >= 0) & (pts[:, 1] < height)
    pts = pts[inside]
    seeds[pts[:, 1].astype(int), pts[:, 0].astype(int)] = 0
    dist, labels = cv2.distanceTransformWithLabels(seeds, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    return dist.astype(np.float32) / cell, labels, pts.astype(np.float32)


def tileable_fbm(size: int, period: float, octaves: int = 5, seed: int = 0) -> np.ndarray:
    """Seamlessly tiling fBm (size x size): value noise on periodic lattices, so the edges wrap exactly."""
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), np.float32)
    amp, total = 1.0, 0.0
    cells = max(2, int(round(size / max(period, 2))))
    for _ in range(octaves):
        if cells > size // 2:
            break
        grid = rng.random((cells, cells)).astype(np.float32)
        padded = np.pad(grid, 2, mode="wrap")
        cell = size / cells
        big = cv2.resize(padded, (int(round((cells + 4) * cell)), int(round((cells + 4) * cell))),
                         interpolation=cv2.INTER_CUBIC)
        o = int(round(2 * cell))
        out += amp * cv2.resize(big[o:o + int(round(cells * cell)), o:o + int(round(cells * cell))], (size, size))
        total += amp
        amp *= 0.5
        cells *= 2
    out /= max(total, 1e-6)
    lo, hi = np.percentile(out, 0.5), np.percentile(out, 99.5)
    return np.clip((out - lo) / max(hi - lo, 1e-6), 0, 1).astype(np.float32)


def perspective_coords(width: int, height: int, horizon_y: float, camera_height: float = 1.0,
                       focal: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ground-plane coordinates for every pixel below the horizon (pinhole camera looking level).

    Returns (X, Z, valid): world X (sideways) and Z (distance) in camera-height units, and a mask of rows
    below the horizon. Use them to sample tileable textures so detail shrinks toward the horizon.
    """
    focal = focal or width * 0.9
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    dy = ys - horizon_y
    valid = dy > 0.5
    z = np.where(valid, camera_height * focal / np.maximum(dy, 0.5), 0)
    x = (xs - width / 2) * z / focal
    return x.astype(np.float32), z.astype(np.float32), valid


def sample_tiled(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear sample of a tileable texture at pixel coords (u, v), wrapping around."""
    th, tw = tex.shape[:2]
    return cv2.remap(tex, np.mod(u, tw).astype(np.float32), np.mod(v, th).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
