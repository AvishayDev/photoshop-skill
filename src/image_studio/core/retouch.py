"""Retouching: clone stamp, healing, inpainting and background separation.

All functions work on layer-local uint8 RGBA arrays and return new arrays.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..errors import ValidationError
from .selection import brush_dab, dab_positions, stamp


def _check_points(strokes, w, h, label):
    if not strokes or not any(strokes):
        raise ValidationError(f"{label}: at least one stroke with one point is required")
    for s in strokes:
        for p in s:
            if len(p) < 2 or not all(isinstance(v, (int, float)) for v in p[:2]):
                raise ValidationError(f"{label}: points must be [x, y] numbers")
            if not (-w <= p[0] <= 2 * w and -h <= p[1] <= 2 * h):
                raise ValidationError(f"{label}: point {p} is far outside the layer")


def clone_stamp(target: np.ndarray, source: np.ndarray, source_point: tuple[float, float],
                strokes: list[list[list[float]]], *, size: float = 30, hardness: float = 0.6,
                opacity: float = 1.0, aligned: bool = True, spacing: float = 0.12) -> tuple[np.ndarray, dict]:
    """Photoshop/GIMP-style clone stamp.

    ``source_point`` is sampled for the first dab of the first stroke; the offset
    (source - first target point) is kept for all later dabs when ``aligned`` is
    true, or reset to ``source_point`` at the start of every stroke otherwise.
    Source pixels are read from a snapshot taken before painting so results are
    deterministic. Coordinates are layer-local (target and source share them).
    """
    h, w = target.shape[:2]
    _check_points(strokes, w, h, "clone_stamp")
    if not 0 < opacity <= 1:
        raise ValidationError("opacity must be within (0, 1]")
    src = source.astype(np.float32) / 255
    out = target.astype(np.float32) / 255
    dab = brush_dab(size, hardness) * opacity
    r = dab.shape[0] // 2
    offset = None
    painted = 0
    for stroke in strokes:
        if not aligned or offset is None:
            first = stroke[0]
            offset = (source_point[0] - first[0], source_point[1] - first[1])
        for pt, _ in dab_positions([stroke], size, spacing):
            cx, cy = int(round(pt[0])), int(round(pt[1]))
            sx, sy = cx + int(round(offset[0])), cy + int(round(offset[1]))
            x0, y0 = cx - r, cy - r
            ok = _blend_patch(out, src, dab, x0, y0, sx - r, sy - r)
            painted += int(ok)
    result = np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)
    return result, {"dabs_painted": painted, "offset": [round(offset[0], 2), round(offset[1], 2)] if offset else None}


def _blend_patch(out, src, dab, tx, ty, sx, sy) -> bool:
    H, W = out.shape[:2]
    SH, SW = src.shape[:2]
    d = dab.shape[0]
    # intersect target and source windows
    x0 = max(0, tx, tx + (0 - sx))
    y0 = max(0, ty, ty + (0 - sy))
    x1 = min(W, tx + d, tx + (SW - sx))
    y1 = min(H, ty + d, ty + (SH - sy))
    if x1 <= x0 or y1 <= y0:
        return False
    dx0, dy0 = x0 - tx, y0 - ty
    a = dab[dy0:dy0 + (y1 - y0), dx0:dx0 + (x1 - x0)][..., None]
    s = src[sy + dy0:sy + dy0 + (y1 - y0), sx + dx0:sx + dx0 + (x1 - x0)]
    t = out[y0:y1, x0:x1]
    t[...] = t * (1 - a) + s * a
    return True


def heal(target: np.ndarray, source_point: tuple[float, float] | None, strokes: list[list[list[float]]], *,
         size: float = 30, hardness: float = 0.5, method: str = "auto") -> tuple[np.ndarray, dict]:
    """Healing brush.

    With a ``source_point``: copies texture from the source offset and blends it
    into the destination with Poisson (gradient-domain) cloning so color and
    lighting adapt to the surroundings (``cv2.seamlessClone``).
    Without one (spot healing): reconstructs the stroked area by inpainting.
    """
    h, w = target.shape[:2]
    _check_points(strokes, w, h, "heal_region")
    mask = np.zeros((h, w), np.float32)
    dab = brush_dab(size, hardness)
    r = dab.shape[0] // 2
    for pt, _ in dab_positions(strokes, size, 0.12):
        stamp(mask, dab, pt[0], pt[1], r)
    m8 = (mask > 0.05).astype(np.uint8) * 255
    if not m8.any():
        raise ValidationError("heal_region: strokes do not touch the layer")
    rgb = np.ascontiguousarray(target[..., :3])
    info: dict = {"pixels_healed": int((m8 > 0).sum())}
    if source_point is None or method == "inpaint":
        res = cv2.inpaint(rgb, m8, max(3, int(size / 4)), cv2.INPAINT_TELEA)
        info["method"] = "inpaint_telea"
    else:
        first = strokes[0][0]
        off = (int(round(source_point[0] - first[0])), int(round(source_point[1] - first[1])))
        M = np.float32([[1, 0, -off[0]], [0, 1, -off[1]]])
        shifted = cv2.warpAffine(rgb, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        ys, xs = np.nonzero(m8)
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        # seamlessClone needs the patch strictly inside the destination
        pad = 2
        if x0 < pad or y0 < pad or x1 > w - pad or y1 > h - pad:
            bordered = cv2.copyMakeBorder(rgb, pad * 4, pad * 4, pad * 4, pad * 4, cv2.BORDER_REFLECT)
            sb = cv2.copyMakeBorder(shifted, pad * 4, pad * 4, pad * 4, pad * 4, cv2.BORDER_REFLECT)
            mb = cv2.copyMakeBorder(m8, pad * 4, pad * 4, pad * 4, pad * 4, cv2.BORDER_CONSTANT, value=0)
            o = pad * 4
            center = (int((x0 + x1) / 2) + o, int((y0 + y1) / 2) + o)
            patch_src = sb[y0 + o:y1 + o, x0 + o:x1 + o]
            patch_mask = mb[y0 + o:y1 + o, x0 + o:x1 + o]
            res = cv2.seamlessClone(patch_src, bordered, patch_mask, center, cv2.NORMAL_CLONE)[o:o + h, o:o + w]
        else:
            center = (int((x0 + x1) / 2), int((y0 + y1) / 2))
            res = cv2.seamlessClone(shifted[y0:y1, x0:x1], rgb, m8[y0:y1, x0:x1], center, cv2.NORMAL_CLONE)
        # feather the hard healing mask edge with the soft brush
        soft = mask[..., None]
        res = (rgb * (1 - soft) + res * soft).astype(np.uint8)
        info["method"] = "poisson_clone"
        info["offset"] = list(off)
    out = target.copy()
    out[..., :3] = res
    return out, info


def inpaint(rgba: np.ndarray, mask: np.ndarray, *, method: str = "telea", radius: int = 5,
            dilate: int = 3) -> np.ndarray:
    m8 = (mask > 0.05).astype(np.uint8) * 255
    if dilate > 0:
        m8 = cv2.dilate(m8, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * dilate + 1, 2 * dilate + 1)))
    flag = {"telea": cv2.INPAINT_TELEA, "navier_stokes": cv2.INPAINT_NS}.get(method)
    if flag is None:
        raise ValidationError("inpaint method must be 'telea' or 'navier_stokes'")
    out = rgba.copy()
    out[..., :3] = cv2.inpaint(np.ascontiguousarray(rgba[..., :3]), m8, radius, flag)
    return out


def grabcut_mask(rgba: np.ndarray, *, rect: tuple[int, int, int, int] | None = None,
                 fg_points: list[list[float]] | None = None, bg_points: list[list[float]] | None = None,
                 iterations: int = 5, point_radius: int = 6) -> np.ndarray:
    """Foreground extraction with OpenCV GrabCut. Returns a soft float mask (1 = subject)."""
    h, w = rgba.shape[:2]
    if h < 8 or w < 8:
        raise ValidationError("Layer too small for background removal")
    rgb = np.ascontiguousarray(rgba[..., :3])
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    if rect is None:
        mx, my = max(2, w // 20), max(2, h // 20)
        rect = (mx, my, w - 2 * mx, h - 2 * my)
    x, y, rw, rh = [int(v) for v in rect]
    if rw < 4 or rh < 4:
        raise ValidationError("rect is too small")
    mask[:] = cv2.GC_BGD
    mask[max(0, y):y + rh, max(0, x):x + rw] = cv2.GC_PR_FGD
    for pts, val in ((fg_points, cv2.GC_FGD), (bg_points, cv2.GC_BGD)):
        for p in pts or []:
            cv2.circle(mask, (int(p[0]), int(p[1])), point_radius, int(val), -1)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(rgb, mask, None, bgd, fgd, max(1, int(iterations)), cv2.GC_INIT_WITH_MASK)
    hard = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1.0, 0.0).astype(np.float32)
    # keep the largest components, refine edge softly
    n, labels, stats, _ = cv2.connectedComponentsWithStats((hard > 0).astype(np.uint8))
    if n > 2:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = 1 + np.flatnonzero(areas >= areas.max() * 0.05)
        hard *= np.isin(labels, keep)
    soft = cv2.GaussianBlur(hard, (0, 0), 1.2)
    if rgba.shape[2] == 4:
        soft *= rgba[..., 3].astype(np.float32) / 255
    return np.clip(soft, 0, 1)
