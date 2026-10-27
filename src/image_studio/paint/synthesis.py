"""Patch-based texture synthesis ("clone stamp" quilting, Efros & Freeman 2001).

Grows a new, larger, non-repeating texture by stamping patches sampled from an exemplar - the automated
version of building texture with the clone stamp tool - and hides the seams with minimum-error boundary
cuts. Use it on a texture region of a licensed reference (bark, fur, water, foliage, sand, stone) to get
material detail that procedural noise cannot imitate.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..errors import ValidationError


def _min_cut(err: np.ndarray) -> np.ndarray:
    """Vertical minimum-error path through ``err`` (h, w). Returns a mask: 1 right of the cut (new patch)."""
    h, w = err.shape
    cost = err.copy()
    for y in range(1, h):
        prev = cost[y - 1]
        left = np.concatenate([[np.inf], prev[:-1]])
        right = np.concatenate([prev[1:], [np.inf]])
        cost[y] += np.minimum(np.minimum(left, prev), right)
    mask = np.zeros((h, w), np.float32)
    x = int(np.argmin(cost[-1]))
    for y in range(h - 1, -1, -1):
        mask[y, x:] = 1
        if y:
            lo, hi = max(0, x - 1), min(w, x + 2)
            x = lo + int(np.argmin(cost[y - 1, lo:hi]))
    return mask


def quilt(exemplar: np.ndarray, width: int, height: int, *, patch: int = 48, overlap: int | None = None,
          tolerance: float = 0.1, seed: int = 0) -> np.ndarray:
    """Synthesize a (height, width, 3) float texture from an exemplar (h, w, 3) float image."""
    ex = np.ascontiguousarray(exemplar[..., :3].astype(np.float32))
    eh, ew = ex.shape[:2]
    patch = int(min(patch, eh - 1, ew - 1))
    if patch < 8:
        raise ValidationError("Exemplar is too small for texture synthesis (need at least ~16x16 px)")
    ov = int(overlap or max(4, patch // 6))
    step = patch - ov
    rng = np.random.default_rng(seed)
    ny, nx = int(np.ceil((height - ov) / step)), int(np.ceil((width - ov) / step))
    H, W = ny * step + ov, nx * step + ov
    out = np.zeros((H, W, 3), np.float32)
    ch, cw = eh - patch + 1, ew - patch + 1
    for iy in range(ny):
        for ix in range(nx):
            y, x = iy * step, ix * step
            cost = np.zeros((ch, cw), np.float32)
            if ix > 0:
                tmpl = out[y:y + patch, x:x + ov]
                cost += cv2.matchTemplate(ex[:, :ew - patch + ov], tmpl, cv2.TM_SQDIFF)[:ch, :cw]
            if iy > 0:
                tmpl = out[y:y + ov, x:x + patch]
                cost += cv2.matchTemplate(ex[:eh - patch + ov, :], tmpl, cv2.TM_SQDIFF)[:ch, :cw]
            if ix == 0 and iy == 0:
                cy, cx = int(rng.integers(0, ch)), int(rng.integers(0, cw))
            else:
                thr = cost.min() * (1 + tolerance) + 1e-6
                cand = np.argwhere(cost <= thr)
                cy, cx = cand[int(rng.integers(0, len(cand)))]
            new = ex[cy:cy + patch, cx:cx + patch]
            mask = np.ones((patch, patch), np.float32)
            if ix > 0:
                err = ((out[y:y + patch, x:x + ov] - new[:, :ov]) ** 2).sum(-1)
                mask[:, :ov] = np.minimum(mask[:, :ov], _min_cut(err))
            if iy > 0:
                err = ((out[y:y + ov, x:x + patch] - new[:ov, :]) ** 2).sum(-1)
                mask[:ov, :] = np.minimum(mask[:ov, :], _min_cut(err.T).T)
            mask = cv2.GaussianBlur(mask, (0, 0), 0.8) if (ix or iy) else mask
            region = out[y:y + patch, x:x + patch]
            out[y:y + patch, x:x + patch] = region * (1 - mask[..., None]) + new * mask[..., None]
    return out[:height, :width]
