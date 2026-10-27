"""Measure reusable patterns on a reference image.

What a painter extracts from studying a photo, as numbers:
    * palette     dominant colours with share and role (base / marks / light / shadow)
    * marks       dark-mark analysis: coverage, count, elongation -> stripes vs spots vs plain
    * period      dominant spatial period (FFT) of the markings, in px and relative to subject height
    * orientation dominant texture direction (structure tensor) and how coherent it is
    * silhouette  the subject's outline as a normalized contour ("search the borders in the images")
    * light       rough key-light direction from the luminance gradient
and a ``suggested`` block with ready-to-save pattern-library entries.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..core.retouch import grabcut_mask
from ..errors import ValidationError
from ..workflows.quality_check import light_direction


def _hex(c: np.ndarray) -> str:
    return "#" + "".join(f"{int(np.clip(v, 0, 1) * 255 + 0.5):02x}" for v in c)


def palette(rgb: np.ndarray, weight: np.ndarray, k: int = 6) -> list[dict[str, Any]]:
    sel = rgb[weight > 0.5]
    if len(sel) < k * 4:
        raise ValidationError("Too few subject pixels to learn a palette")
    if len(sel) > 40000:
        sel = sel[np.random.default_rng(0).choice(len(sel), 40000, replace=False)]
    _, labels, centers = cv2.kmeans(sel.astype(np.float32), k, None,
                                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 1e-4), 3,
                                    cv2.KMEANS_PP_CENTERS)
    share = np.bincount(labels.ravel(), minlength=k) / len(labels)
    lum = centers @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    order = np.argsort(lum)
    return [{"hex": _hex(centers[i]), "share": round(float(share[i]), 3), "luminance": round(float(lum[i]), 3)}
            for i in order if share[i] > 0.002]  # drop empty clusters (images with few distinct colours)


def dominant_period(gray: np.ndarray, weight: np.ndarray) -> dict[str, Any]:
    """Strongest repeating wavelength of the markings (FFT of the masked, windowed luminance)."""
    ys, xs = np.nonzero(weight > 0.5)
    if xs.size < 256:
        return {"period_px": None}
    crop = gray[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    w = weight[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    m = crop[w > 0.5].mean()
    g = (crop - m) * w
    h, wd = g.shape
    win = np.outer(np.hanning(h), np.hanning(wd)).astype(np.float32)
    F = np.abs(np.fft.fftshift(np.fft.fft2(g * win))) ** 2
    cy, cx = h // 2, wd // 2
    yy, xx = np.mgrid[0:h, 0:wd]
    fy, fx = (yy - cy) / h, (xx - cx) / wd
    r = np.hypot(fx, fy)
    valid = (r > 3.0 / max(min(h, wd), 1)) & (r < 0.25)  # periods from ~4 px up to a third of the subject
    if not valid.any():
        return {"period_px": None}
    idx = np.argmax(np.where(valid, F, 0))
    ry, rx = np.unravel_index(idx, F.shape)
    freq = float(r[ry, rx])
    angle = float(np.degrees(np.arctan2(fy[ry, rx], fx[ry, rx]))) % 180  # direction ACROSS the marks
    strength = float(F[ry, rx] / (F[valid].mean() + 1e-9))
    return {"period_px": round(1 / freq, 2), "across_angle_deg": round(angle, 1),
            "peak_to_mean": round(strength, 2)}


def orientation(gray: np.ndarray, weight: np.ndarray) -> dict[str, Any]:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    jxx, jyy, jxy = (gx * gx * weight).sum(), (gy * gy * weight).sum(), (gx * gy * weight).sum()
    ang = 0.5 * np.degrees(np.arctan2(2 * jxy, jxx - jyy))  # dominant gradient direction
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / max(jxx + jyy, 1e-9)
    return {"gradient_angle_deg": round(float(ang % 180), 1),
            "edge_direction_deg": round(float((ang + 90) % 180), 1), "coherence": round(float(coh), 3)}


def marks(gray: np.ndarray, weight: np.ndarray) -> dict[str, Any]:
    """Threshold the dark markings inside the subject and describe their shapes."""
    sel = gray[weight > 0.5]
    if sel.size < 256:
        return {"type": "unknown"}
    u8 = np.clip(gray * 255, 0, 255).astype(np.uint8)
    sel_u8 = np.clip(sel * 255, 0, 255).astype(np.uint8).reshape(-1, 1)
    thr, _ = cv2.threshold(sel_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = ((u8 <= thr) & (weight > 0.5)).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    coverage = float(dark.sum() / max((weight > 0.5).sum(), 1))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(dark)
    elong, widths = [], []
    min_area = max(12, int((weight > 0.5).sum() * 0.0005))
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            continue
        ys, xs = np.nonzero(labels == i)
        cov = np.cov(np.stack([xs, ys]).astype(np.float32)) if xs.size > 2 else np.eye(2)
        ev = np.sort(np.linalg.eigvalsh(cov))
        e = float(np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-6)))
        elong.append(e)
        widths.append(float(stats[i, cv2.CC_STAT_AREA]) / max(4 * np.sqrt(ev[1]), 1))
    count = len(elong)
    me = float(np.median(elong)) if elong else 0.0
    if count < 3 or coverage < 0.04:
        kind = "plain"
    elif me > 2.6:
        kind = "stripes"
    elif me < 1.9:
        kind = "spots"
    else:
        kind = "mottled"
    return {"type": kind, "coverage": round(coverage, 3), "count": count, "median_elongation": round(me, 2),
            "median_width_px": round(float(np.median(widths)), 2) if widths else None,
            "threshold_luminance": round(float(thr) / 255, 3)}


def silhouette(weight: np.ndarray, points: int = 72) -> dict[str, Any] | None:
    """Largest outer contour, resampled evenly and normalized: y in 0..1 over the subject's height, x in the
    same units (so it can be drawn by a figure 'contour' part)."""
    m = (weight > 0.5).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)[:, 0, :].astype(np.float32)
    seg = np.hypot(*np.diff(np.vstack([c, c[:1]]), axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, cum[-1], points, endpoint=False)
    pts = np.stack([np.interp(t, cum, np.append(c[:, 0], c[0, 0])),
                    np.interp(t, cum, np.append(c[:, 1], c[0, 1]))], axis=1)
    x0, y0 = pts.min(0)
    hgt = max(float(pts[:, 1].max() - y0), 1.0)
    norm = (pts - [x0, y0]) / hgt
    return {"aspect": round(float(norm[:, 0].max()), 4), "points": [[round(float(a), 4), round(float(b), 4)]
                                                                     for a, b in norm],
            "area_fraction_of_box": round(float(cv2.contourArea(c)) / max((np.ptp(c[:, 0]) * np.ptp(c[:, 1])), 1), 3)}


def learn_from_image(rgba: np.ndarray, *, rect: list[int] | None = None, mask: np.ndarray | None = None,
                     name: str = "subject", fg_points: list[list[float]] | None = None,
                     bg_points: list[list[float]] | None = None) -> dict[str, Any]:
    """Learn palette, markings, period, orientation, silhouette and light from an RGBA uint8 image.

    rect: [x, y, w, h] around the subject -> GrabCut separates it (silhouette + subject-only stats).
    mask: explicit subject mask (float 0..1) instead. Neither: the whole image is treated as a texture.
    """
    if rgba.ndim != 3 or rgba.shape[2] not in (3, 4):
        raise ValidationError("learn_from_image needs an RGB(A) image")
    if rgba.shape[2] == 3:
        rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, np.uint8)])
    rgb = rgba[..., :3].astype(np.float32) / 255
    if mask is not None:
        weight = mask.astype(np.float32)
        mode = "mask"
    elif rect is not None or fg_points:
        weight = grabcut_mask(rgba, rect=tuple(rect) if rect else None, fg_points=fg_points, bg_points=bg_points)
        mode = "grabcut"
    else:
        weight = np.ones(rgba.shape[:2], np.float32)
        mode = "texture"
    gray = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    inner = cv2.erode((weight > 0.5).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
    if inner.sum() < 256:
        inner = (weight > 0.5).astype(np.float32)
    pal = palette(rgb, inner)
    mk = marks(gray, inner)
    per = dominant_period(gray, inner)
    ori = orientation(gray, inner)
    sil = silhouette(weight) if mode != "texture" else None
    ys = np.nonzero(weight.max(axis=1) > 0.5)[0]
    subj_h = float(ys.max() - ys.min() + 1) if ys.size else float(rgba.shape[0])
    light = light_direction(np.dstack([rgb * inner[..., None] + 0.5 * (1 - inner[..., None]), inner]))
    out: dict[str, Any] = {"mode": mode, "subject_height_px": subj_h, "subject_fraction":
                           round(float((weight > 0.5).mean()), 3), "palette": pal, "marks": mk, "period": per,
                           "orientation": ori, "light": light}
    if sil:
        out["silhouette"] = sil
    # suggestions the agent can review and save to the pattern library
    sugg: list[dict[str, Any]] = []
    base = max(pal, key=lambda c: c["share"])
    darkest, lightest = pal[0], pal[-1]
    sugg.append({"id": f"palette/{name}", "kind": "palette", "title": f"{name} palette",
                 "params": {"colors": [c["hex"] for c in pal], "base": base["hex"], "marks": darkest["hex"],
                            "light": lightest["hex"], "shares": [c["share"] for c in pal]}})
    if mk.get("type") in ("stripes", "spots", "mottled") and per.get("period_px"):
        rel = round(per["period_px"] / subj_h, 4)
        params: dict[str, Any] = {"type": "stripes" if mk["type"] == "stripes" else "spots",
                                  "color": darkest["hex"]}
        if params["type"] == "stripes":
            params.update(period=rel, thickness=round(min(0.6, max(0.15, mk["coverage"] * 1.1)), 2),
                          across_angle_deg=per["across_angle_deg"])
        else:
            params.update(size=round((mk.get("median_width_px") or per["period_px"] / 3) / subj_h, 4))
        sugg.append({"id": f"texture/{name}-{params['type']}", "kind": "texture",
                     "title": f"{name} {params['type']} (measured)", "params": params,
                     "note": "period/size are fractions of the subject height (figure units)"})
    if sil:
        sugg.append({"id": f"silhouette/{name}", "kind": "silhouette", "title": f"{name} silhouette",
                     "params": {"aspect": sil["aspect"], "points": sil["points"]},
                     "note": "Use as a figure part: {'shape': 'contour', 'points': ...}; mirror x for the "
                             "opposite facing."})
    out["suggested"] = sugg
    return _plain(out)


def _plain(o: Any) -> Any:
    """Convert numpy scalars so results are JSON-serializable."""
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o
