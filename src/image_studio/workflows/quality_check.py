"""Objective image measurements and defect heuristics for the inspect -> correct loop.

These checks complement (never replace) the agent looking at the preview with
its own vision. They flag measurable problems: clipping, color casts, flat
contrast, hard seams along layer boundaries, halos, repeated clone patterns,
and subject/background mismatches in brightness, color, sharpness and noise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..core.color import luminance, rgb_to_lab
from ..errors import ValidationError


def _rgb(arr: np.ndarray) -> np.ndarray:
    a = arr.astype(np.float32) / 255 if arr.dtype == np.uint8 else arr.astype(np.float32)
    if a.shape[-1] == 4:
        alpha = a[..., 3:4]
        a = a[..., :3] * alpha + 0.5 * (1 - alpha)
    return a[..., :3]


def sharpness(gray: np.ndarray, weight: np.ndarray | None = None) -> float:
    lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F)
    if weight is not None:
        sel = weight > 0.5
        return float(lap[sel].var()) if sel.sum() > 16 else 0.0
    return float(lap.var())


def noise_level(gray: np.ndarray, weight: np.ndarray | None = None) -> float:
    """Robust noise sigma estimate (median absolute deviation of a high-pass residual)."""
    resid = gray.astype(np.float32) - cv2.medianBlur((gray * 255).astype(np.uint8), 3).astype(np.float32) / 255
    vals = resid[weight > 0.5] if weight is not None else resid.ravel()
    if vals.size < 16:
        return 0.0
    return float(1.4826 * np.median(np.abs(vals - np.median(vals))))


def image_stats(arr: np.ndarray, weight: np.ndarray | None = None) -> dict[str, Any]:
    rgb = _rgb(arr)
    lum = luminance(rgb)
    sel = (weight > 0.5) if weight is not None else np.ones(lum.shape, bool)
    if sel.sum() < 16:
        raise ValidationError("Too few pixels to measure")
    lv = lum[sel]
    lab = rgb_to_lab(rgb)[sel]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    return {
        "mean_luminance": round(float(lv.mean()), 4),
        "luminance_p05": round(float(np.percentile(lv, 5)), 4),
        "luminance_p95": round(float(np.percentile(lv, 95)), 4),
        "contrast_std": round(float(lv.std()), 4),
        "clipped_highlights": round(float((lv > 0.985).mean()), 4),
        "crushed_shadows": round(float((lv < 0.015).mean()), 4),
        "mean_saturation": round(float(hsv[..., 1][sel].mean()), 4),
        "lab_mean": [round(float(v), 2) for v in lab.mean(0)],
        "warmth_b": round(float(lab[:, 2].mean()), 2),
        "tint_a": round(float(lab[:, 1].mean()), 2),
        "sharpness": round(sharpness(lum, weight), 6),
        "noise_sigma": round(noise_level(lum, weight), 5),
    }


def dominant_colors(arr: np.ndarray, k: int = 6) -> list[dict[str, Any]]:
    rgb = _rgb(arr)
    small = cv2.resize(rgb, (min(160, rgb.shape[1]), min(160, rgb.shape[0])), interpolation=cv2.INTER_AREA)
    data = small.reshape(-1, 3).astype(np.float32)
    k = max(1, min(k, len(data)))
    _, labels, centers = cv2.kmeans(data, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-3),
                                    3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k) / len(labels)
    order = np.argsort(-counts)
    return [{"hex": "#" + "".join(f"{int(c * 255):02x}" for c in centers[i]), "share": round(float(counts[i]), 3)}
            for i in order]


def light_direction(arr: np.ndarray) -> dict[str, Any]:
    """Very rough key-light direction from the large-scale luminance gradient (image coords, y down)."""
    lum = luminance(_rgb(arr))
    small = cv2.resize(lum, (64, 64), interpolation=cv2.INTER_AREA)
    blur = cv2.GaussianBlur(small, (0, 0), 6)
    gx = float(cv2.Sobel(blur, cv2.CV_32F, 1, 0).mean())
    gy = float(cv2.Sobel(blur, cv2.CV_32F, 0, 1).mean())
    mag = float(np.hypot(gx, gy))
    if mag < 1e-3:
        return {"direction": "even / undetermined", "confidence": "low"}
    angle = float(np.degrees(np.arctan2(gy, gx)))  # direction toward brighter side
    names = ["right", "lower-right", "bottom", "lower-left", "left", "upper-left", "top", "upper-right"]
    name = names[int(((angle % 360) + 22.5) // 45) % 8]
    return {"brighter_toward": name, "angle_deg": round(angle, 1), "strength": round(mag, 4),
            "confidence": "medium" if mag > 0.02 else "low",
            "note": "Global brightness gradient only; verify light direction visually from shadows."}


def repeated_patches(arr: np.ndarray, patch: int = 16, min_std: float = 0.04, max_report: int = 5) -> list[dict]:
    """Find identical textured patches at different positions (typical clone-stamp artifact)."""
    rgb = (_rgb(arr) * 255).astype(np.uint8)
    h, w = rgb.shape[:2]
    seen: dict[bytes, tuple[int, int]] = {}
    hits = []
    step = patch // 2
    q = (rgb // 8).astype(np.uint8)
    for y in range(0, h - patch, step):
        for x in range(0, w - patch, step):
            p = rgb[y:y + patch, x:x + patch]
            if p.std() / 255 < min_std:
                continue
            key = q[y:y + patch, x:x + patch].tobytes()
            if key in seen:
                sx, sy = seen[key]
                if abs(sx - x) > patch or abs(sy - y) > patch:
                    hits.append({"a": [sx, sy], "b": [x, y], "size": patch})
                    if len(hits) >= max_report:
                        return hits
            else:
                seen[key] = (x, y)
    return hits


def seam_score(canvas: np.ndarray, layer_alpha_doc: np.ndarray) -> dict[str, Any]:
    """Edge contrast along a composited layer's boundary vs. inside/outside it.
    High ratios indicate hard cut-out edges or halos."""
    lum = luminance(_rgb(canvas))
    a = (layer_alpha_doc > 0.5).astype(np.uint8)
    if a.sum() < 50:
        return {"available": False}
    k = np.ones((3, 3), np.uint8)
    edge = cv2.dilate(a, k) - cv2.erode(a, k)
    grad = cv2.magnitude(cv2.Sobel(lum, cv2.CV_32F, 1, 0), cv2.Sobel(lum, cv2.CV_32F, 0, 1))
    interior = cv2.erode(a, k, iterations=4).astype(bool)
    exterior = (cv2.dilate(a, k, iterations=6) - cv2.dilate(a, k, iterations=3)).astype(bool)
    e = float(grad[edge.astype(bool)].mean()) if edge.any() else 0.0
    ref = np.concatenate([grad[interior], grad[exterior]]) if interior.any() or exterior.any() else np.array([1e-3])
    ratio = e / max(float(np.median(ref)) + 1e-3, 1e-3)
    # halo: thin bright/dark rim just outside the alpha edge
    rim = (cv2.dilate(a, k, iterations=2) - a).astype(bool)
    halo = float(lum[rim].mean() - lum[exterior].mean()) if rim.any() and exterior.any() else 0.0
    return {"available": True, "edge_gradient_ratio": round(ratio, 2), "halo_luminance_delta": round(halo, 4)}


def defects(stats: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    if stats["clipped_highlights"] > 0.02:
        out.append({"severity": "medium", "issue": f"{stats['clipped_highlights']:.1%} of pixels are clipped white",
                    "fix": "Lower exposure/levels highlights or add a highlight roll-off curve."})
    if stats["crushed_shadows"] > 0.04:
        out.append({"severity": "medium", "issue": f"{stats['crushed_shadows']:.1%} of pixels are crushed black",
                    "fix": "Lift the curve's black point slightly unless deep blacks are intended."})
    if stats["contrast_std"] < 0.08:
        out.append({"severity": "low", "issue": "Low global contrast (flat image)",
                    "fix": "Add an S-curve or levels adjustment layer."})
    if abs(stats["tint_a"]) > 12 or abs(stats["warmth_b"]) > 30:
        out.append({"severity": "low", "issue": f"Strong color cast (Lab a={stats['tint_a']}, b={stats['warmth_b']})",
                    "fix": "Check it is intentional; otherwise use temperature_tint or color_balance."})
    return out


def inspect_array(arr: np.ndarray) -> dict[str, Any]:
    stats = image_stats(arr)
    report = {"stats": stats, "dominant_colors": dominant_colors(arr), "light": light_direction(arr),
              "defects": defects(stats)}
    reps = repeated_patches(arr)
    if reps:
        report["defects"].append({"severity": "medium", "issue": f"{len(reps)}+ identical textured patches found "
                                  "(possible visible clone-stamp repetition)", "fix": "Re-clone from varied sources "
                                  "with lower opacity, or heal over the repeats.", "locations": reps})
    return report


def compare_arrays(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    if a.shape[:2] != b.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    la, lb = luminance(_rgb(a)), luminance(_rgb(b))
    diff = np.abs(_rgb(a) - _rgb(b)).mean(-1)
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    mu_a, mu_b = cv2.GaussianBlur(la, (0, 0), 1.5), cv2.GaussianBlur(lb, (0, 0), 1.5)
    s_a = cv2.GaussianBlur(la * la, (0, 0), 1.5) - mu_a ** 2
    s_b = cv2.GaussianBlur(lb * lb, (0, 0), 1.5) - mu_b ** 2
    s_ab = cv2.GaussianBlur(la * lb, (0, 0), 1.5) - mu_a * mu_b
    ssim = ((2 * mu_a * mu_b + C1) * (2 * s_ab + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (s_a + s_b + C2))
    changed = diff > 0.04
    ys, xs = np.nonzero(changed)
    out = {"ssim": round(float(ssim.mean()), 4), "mean_abs_diff": round(float(diff.mean()), 5),
           "changed_fraction": round(float(changed.mean()), 5)}
    if len(xs):
        out["changed_bounds"] = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
    out["_diff_map"] = diff
    return out


def save_heatmap(diff: np.ndarray, path: Path) -> None:
    norm = np.clip(diff / max(float(diff.max()), 1e-6), 0, 1)
    heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    Image.fromarray(cv2.cvtColor(heat, cv2.COLOR_BGR2RGB)).save(path)


def integration_report(canvas_below: np.ndarray, subject: np.ndarray, subject_alpha_doc: np.ndarray,
                       full_canvas: np.ndarray) -> dict[str, Any]:
    """Compare a composited subject with the backdrop around it."""
    a = subject_alpha_doc
    k = np.ones((5, 5), np.uint8)
    ring = (cv2.dilate((a > 0.5).astype(np.uint8), k, iterations=12) -
            cv2.dilate((a > 0.5).astype(np.uint8), k, iterations=2)).astype(np.float32)
    ring *= canvas_below[..., 3]
    s_stats = image_stats(full_canvas, a)
    b_stats = image_stats(canvas_below, ring)
    findings = []
    dl = s_stats["mean_luminance"] - b_stats["mean_luminance"]
    if abs(dl) > 0.12:
        findings.append({"issue": f"Subject is {'brighter' if dl > 0 else 'darker'} than its surroundings by "
                                  f"{abs(dl):.2f} luminance", "fix": "exposure/curves on the subject (clipped "
                                  "adjustment layer), unless the subject is meant to be lit differently."})
    dw = s_stats["warmth_b"] - b_stats["warmth_b"]
    if abs(dw) > 8:
        findings.append({"issue": f"Subject is {'warmer' if dw > 0 else 'cooler'} than surroundings (Lab b delta "
                                  f"{dw:.1f})", "fix": "match_color or temperature_tint on the subject."})
    if b_stats["sharpness"] > 0 and s_stats["sharpness"] / max(b_stats["sharpness"], 1e-6) > 3:
        findings.append({"issue": "Subject is much sharper than the surrounding area (depth-of-field mismatch?)",
                         "fix": "Slight gaussian blur on the subject, or sharpen the in-focus background plane."})
    if b_stats["noise_sigma"] > 0.004 and s_stats["noise_sigma"] < b_stats["noise_sigma"] * 0.5:
        findings.append({"issue": "Subject is cleaner (less grain) than the backdrop",
                         "fix": f"add_noise on the subject with amount ~{b_stats['noise_sigma']:.3f}."})
    if s_stats["contrast_std"] > b_stats["contrast_std"] * 1.8 and b_stats["contrast_std"] > 0.02:
        findings.append({"issue": "Subject contrast is much higher than the scene (haze/atmosphere mismatch?)",
                         "fix": "Reduce subject contrast or add atmospheric haze over it if it is distant."})
    seam = seam_score(full_canvas, a)
    if seam.get("available") and seam["edge_gradient_ratio"] > 4:
        findings.append({"issue": f"Hard cut-out edge (edge/texture gradient ratio {seam['edge_gradient_ratio']})",
                         "fix": "feather_mask 1-2 px, or edit_layer_mask blur/contrast; check for halos."})
    if seam.get("available") and abs(seam["halo_luminance_delta"]) > 0.08:
        findings.append({"issue": "Bright/dark halo around the subject edge",
                         "fix": "shrink the mask 1-2 px (edit_layer_mask operation=shrink) and refeather."})
    return {"subject": s_stats, "surroundings": b_stats, "edge": seam, "findings": findings}
