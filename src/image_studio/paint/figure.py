"""Data-driven subjects: a figure is a list of parts (shapes) + materials (colour, pattern, fur) + details.

A *figure spec* is plain JSON so it can live in the pattern library and be reused/refined across tasks::

    {
      "aspect": 2.2,                       # width / height of the figure's box
      "parts": [                           # drawn in order (back to front)
        {"name": "far hind leg", "shape": "limb", "points": [[1.6, 0.45], [1.7, 0.75], [1.62, 0.98]],
         "radii": [0.11, 0.06, 0.05], "material": "coat", "shade_factor": 0.75},
        {"name": "body", "shape": "ellipse", "center": [1.1, 0.42], "radii": [0.62, 0.22], "angle": -3,
         "material": "coat"},
        {"name": "head", "shape": "polygon", "points": [[...]], "smooth": true, "material": "coat",
         "axis": [[0.3, 0.2], [0.3, 0.5]]},
        {"name": "train", "shape": "feathers", "base": [..], "tip_path": [[..], [..]], "count": 60, ...}
      ],
      "materials": {"coat": {"colors": ["#b85a1c", "#e0913f"], "belly": "#efe4d2", "belly_from": 0.45,
                              "pattern": {"type": "stripes", "period": 0.07, "thickness": 0.42,
                                          "color": "#17100b"},
                              "fur": {"length": 0.03, "density": 0.09}}},
      "details": [{"type": "eye", "center": [0.2, 0.3], "radius": 0.025, "iris": "#d99a22"}, ...],
      "lighting": {"wrap": 0.4, "rim": 0.3, "specular": 0.05, "depth": 0.25}
    }

Coordinates are in figure units: y from 0 (top) to 1 (bottom of the box), x from 0 to ``aspect``; sizes
(radii, widths, pattern periods, fur length) are fractions of the figure height. The figure is rendered
into a local box, mirrored if ``facing`` is "right" (specs are authored facing left), and placed on the
canvas with its box bottom at ``ground_y``.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from ..errors import ValidationError
from . import brush, patterns, shading, shapes
from .canvas import ColorLike, mix, ramp, rgb, smoothstep
from .noise import fbm

PART_SHAPES = ("ellipse", "limb", "polygon", "blob", "feathers", "contour")
DETAIL_TYPES = ("eye", "ellipse", "polygon", "stroke", "eyespots")


def _axis(part: dict[str, Any], S: float, ox: float, oy: float) -> tuple[np.ndarray, np.ndarray]:
    if "axis" in part:
        a, b = part["axis"]
        return np.array([ox + a[0] * S, oy + a[1] * S]), np.array([ox + b[0] * S, oy + b[1] * S])
    sh = part["shape"]
    if sh == "ellipse":
        cx, cy = part["center"]
        rx, _ = part["radii"]
        ang = np.radians(part.get("angle", 0))
        d = np.array([np.cos(ang), np.sin(ang)]) * rx * S
        c = np.array([ox + cx * S, oy + cy * S])
        return c - d, c + d
    if sh in ("limb",):
        p = part["points"]
        return np.array([ox + p[0][0] * S, oy + p[0][1] * S]), np.array([ox + p[-1][0] * S, oy + p[-1][1] * S])
    pts = np.asarray(part.get("points", [[0, 0], [1, 0]]), np.float32)
    xs = pts[:, 0] * S + ox
    ym = float(pts[:, 1].mean() * S + oy)
    return np.array([xs.min(), ym]), np.array([xs.max(), ym])


def _part_mask(part: dict[str, Any], w: int, h: int, S: float, ox: float, oy: float, seed: int) -> np.ndarray:
    sh = part["shape"]
    f = part.get("feather", 0.6)
    if sh == "ellipse":
        cx, cy = part["center"]
        rx, ry = part["radii"]
        return shapes.ellipse(w, h, ox + cx * S, oy + cy * S, rx * S, ry * S, part.get("angle", 0), feather=f)
    if sh == "limb":
        pts = [(ox + x * S, oy + y * S) for x, y in part["points"]]
        return shapes.bent_capsule(w, h, pts, [r * S for r in part["radii"]], feather=f)
    if sh in ("polygon", "contour"):
        pts = [(ox + x * S, oy + y * S) for x, y in part["points"]]
        return shapes.polygon(w, h, pts, feather=f, smooth=part.get("smooth", sh == "polygon"))
    if sh == "blob":
        cx, cy = part["center"]
        return shapes.blob(w, h, ox + cx * S, oy + cy * S, part["radius"] * S, part.get("irregularity", 0.2),
                           seed=seed, squash=part.get("squash", 1.0), feather=f)
    raise ValidationError(f"Unknown part shape '{sh}'", details={"shapes": PART_SHAPES})


def _feathers(part: dict[str, Any], w: int, h: int, S: float, ox: float, oy: float, seed: int,
              materials: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Peacock-style train: long coverts from a common base, each ending in an eyespot. Tips are spread
    along ``tip_path``; longer feathers are painted first so the shorter ones lie on top and their eyespots
    form staggered rows along the train, as on a real bird. Each vane is painted as filament barbs."""
    rng = np.random.default_rng(seed)
    mat = materials.get(part.get("material", ""), {})
    count = int(part.get("count", 60))
    base = np.array(part["base"], np.float32) * S + (ox, oy)
    tip_path = shapes.catmull_rom([(ox + x * S, oy + y * S) for x, y in part["tip_path"]], closed=False, samples=20)
    seg = np.hypot(*np.diff(tip_path, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    barb_cols = np.stack([rgb(c) for c in mat.get("barb_colors", ["#5f6b1d", "#8a8a2a", "#3f5a1f"])]) * 255
    shaft_col = (rgb(mat.get("shaft_color", "#c9b98a")) * 255).tolist()
    eye_cols = mat.get("eye_colors", ["#0b1d4a", "#1d5fa8", "#22a08a", "#c49a2a", "#6f8a2a"])
    eye_r = float(mat.get("eye_radius", 0.035)) * S
    width_ = float(part.get("width", 0.05)) * S
    spread = float(part.get("spread", 0.02)) * S
    img = np.zeros((h, w, 3), np.uint8)
    cov = np.zeros((h, w), np.uint8)
    ts = np.sort(rng.uniform(0.05, 1.0, count) ** 0.8)[::-1]  # long (far tip) first
    for t in ts:
        d = t * cum[-1]
        tip = np.array([np.interp(d, cum, tip_path[:, 0]), np.interp(d, cum, tip_path[:, 1])])
        tip += rng.normal(0, spread, 2)
        b = base + rng.normal(0, width_ * 0.25, 2)
        v = tip - b
        L = float(np.hypot(*v))
        if L < 6:
            continue
        nrm = np.array([-v[1], v[0]]) / L
        mid = (b + tip) / 2 + nrm * rng.normal(0, 0.05) * L
        shaft = shapes.catmull_rom([b, mid, tip], closed=False, samples=max(12, int(L / 6)))
        tangent = np.gradient(shaft, axis=0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-6)
        n2 = np.stack([-tangent[:, 1], tangent[:, 0]], 1)
        fw = width_ * rng.uniform(0.75, 1.2)
        col = barb_cols[int(rng.integers(0, len(barb_cols)))] * rng.uniform(0.8, 1.15)
        sl = np.linspace(0, 1, len(shaft))
        # barbs: filaments from the shaft, swept toward the tip, longest near the eyespot
        nb = int(len(shaft) * 2.2)
        idx = rng.integers(0, len(shaft), nb)
        for i in idx:
            frac = sl[i]
            blen = fw * (0.25 + 0.75 * frac ** 0.7) * rng.uniform(0.6, 1.1)
            side = 1 if rng.random() < 0.5 else -1
            dirv = n2[i] * side * 0.8 + tangent[i] * 0.6
            e = shaft[i] + dirv / np.linalg.norm(dirv) * blen
            c = np.clip(col * rng.uniform(0.75, 1.2) * (0.7 + 0.3 * frac), 0, 255).tolist()
            p0 = (int(shaft[i][0] * 16), int(shaft[i][1] * 16))
            p1 = (int(e[0] * 16), int(e[1] * 16))
            cv2.line(img, p0, p1, c, 1, cv2.LINE_AA, 4)
            cv2.line(cov, p0, p1, 235, 1, cv2.LINE_AA, 4)
        pts16 = np.round(shaft * 16).astype(np.int32)
        th = max(1, int(round(fw * 0.07)))
        cv2.polylines(img, [pts16], False, shaft_col, th, cv2.LINE_AA, 4)
        cv2.polylines(cov, [pts16], False, 255, th, cv2.LINE_AA, 4)
        if mat.get("eyespots", True):
            r = eye_r * rng.uniform(0.85, 1.15) * (0.7 + 0.3 * t)
            spot = patterns.eyespot(r, eye_cols)
            ang = np.degrees(np.arctan2(v[1], v[0])) - 90
            sh_, sw_ = spot.shape[:2]
            M = cv2.getRotationMatrix2D((sw_ / 2, sh_ / 2), -ang, 1.0)
            spot = cv2.warpAffine(spot, M, (sw_, sh_))
            c = tip - v / L * r * 1.2
            x0, y0 = int(c[0] - sw_ / 2), int(c[1] - sh_ / 2)
            xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0 + sw_), min(h, y0 + sh_)
            if xb > xa and yb > ya:
                sp = spot[ya - y0:yb - y0, xa - x0:xb - x0]
                a = sp[..., 3:4]
                reg = img[ya:yb, xa:xb].astype(np.float32)
                img[ya:yb, xa:xb] = np.clip(reg * (1 - a) + sp[..., :3] * 255 * a, 0, 255).astype(np.uint8)
                cr = cov[ya:yb, xa:xb].astype(np.float32)
                cov[ya:yb, xa:xb] = np.maximum(cr, a[..., 0] * 255).astype(np.uint8)
    alpha = cov.astype(np.float32) / 255
    out = img.astype(np.float32) / 255
    out = np.where(alpha[..., None] > 0, out / np.maximum(alpha[..., None], 1e-3), 0)
    return np.clip(out, 0, 1), alpha


def _resolve_pattern(pat: Any) -> dict[str, Any] | None:
    """A material pattern may reference the pattern library: "texture/tiger-stripes" or
    {"ref": "texture/tiger-stripes", ...overrides}."""
    if not pat:
        return None
    if isinstance(pat, str):
        pat = {"ref": pat}
    if "ref" in pat:
        from ..patterns.library import PatternLibrary
        base = dict(PatternLibrary().get(pat["ref"]).params)
        pat = {**base, **{k: v for k, v in pat.items() if k != "ref"}}
    return pat


def _material_color(mat: dict[str, Any], part: dict[str, Any], u: np.ndarray, vn: np.ndarray, w: int, h: int,
                    S: float, seed: int) -> np.ndarray:
    cols = mat.get("colors", ["#888888"])
    if mat.get("gradient", "across") == "along":
        t = np.clip(u, 0, 1)
    else:
        t = np.clip(vn * 0.5 + 0.5, 0, 1)
    if part.get("flip_gradient"):
        t = 1 - t
    base = ramp(t, cols) if len(cols) > 1 else np.broadcast_to(rgb(cols[0]), t.shape + (3,)).copy()
    var = float(mat.get("variation", 0.08))
    if var:
        n = fbm(w, h, max(S * 0.15, 4), 4, seed=seed + 3)
        base = base * (1 + (n[..., None] - 0.5) * 2 * var)
    if "belly" in mat:
        bf = float(mat.get("belly_from", 0.5))
        bm = smoothstep(bf - 0.12, bf + 0.12, vn * (1 if not part.get("belly_up") else -1))
        bm *= part.get("belly", 1.0)
        base = mix(base, np.broadcast_to(rgb(mat["belly"]), base.shape), bm)
    if "tint" in part:
        base = mix(base, np.broadcast_to(rgb(part["tint"]), base.shape), part.get("tint_amount", 0.5))
    return base


def render_figure(spec: dict[str, Any], *, height: float, light_azimuth: float = 200.0, light_elevation: float = 40.0,
                  key_color: ColorLike = "#fff2dc", ambient_color: ColorLike = "#93a8c4", ambient: float = 0.35,
                  facing: str = "left", seed: int = 0) -> np.ndarray:
    """Render a figure spec into a tight RGBA image of the given pixel ``height`` (plus margin).

    Returns an (h, w, 4) float image; the figure box starts at (pad, pad) where pad = 6% of height.
    """
    aspect = float(spec.get("aspect", 1.0))
    S = float(height)
    pad = int(S * 0.06) + 4
    w, h = int(aspect * S) + 2 * pad, int(S) + 2 * pad
    ox = oy = pad
    az = light_azimuth if facing == "left" else 180 - light_azimuth  # authored facing left; mirrored later
    mats = spec.get("materials", {})
    lit = spec.get("lighting", {})
    img = np.zeros((h, w, 3), np.float32)
    alpha = np.zeros((h, w), np.float32)
    hgt = np.zeros((h, w), np.float32)
    flow = np.zeros((h, w), np.float32)
    fur_mask = np.zeros((h, w), np.float32)
    fur_params: dict[str, Any] = {}
    for i, part in enumerate(spec.get("parts", [])):
        if part["shape"] not in PART_SHAPES:
            raise ValidationError(f"Unknown part shape '{part['shape']}'", details={"shapes": PART_SHAPES})
        pseed = seed * 131 + i * 17
        if part["shape"] == "feathers":
            fimg, fa = _feathers(part, w, h, S, ox, oy, pseed, mats)
            img = img * (1 - fa[..., None]) + fimg * fa[..., None]
            ph = shading.height_from_mask(fa, radius=S * 0.03) * 0.25
            hgt = np.where(fa > 0.5, ph, hgt)
            alpha = np.maximum(alpha, fa)
            fur_mask *= 1 - fa
            continue
        m = _part_mask(part, w, h, S, ox, oy, pseed)
        mat = mats.get(part.get("material", ""), {"colors": [part.get("color", "#888888")]})
        p0, p1 = _axis(part, S, ox, oy)
        u, v = shapes.axis_coords(w, h, p0, p1)
        thick = float(part.get("radii", [0, 0.1])[1] if part["shape"] == "ellipse" else
                      max(part.get("radii", [0.08])) if part["shape"] == "limb" else part.get("thickness", 0.15))
        vn = np.clip(v / max(thick * S, 1), -1.5, 1.5)
        col = _material_color(mat, part, u, vn, w, h, S, pseed)
        pat = _resolve_pattern(mat.get("pattern"))
        if pat and part.get("pattern", True):
            scale = float(part.get("pattern_scale", 1.0))
            along_px = u * float(np.hypot(*(p1 - p0)))
            ptype = pat.get("type", "stripes")
            if ptype == "stripes":
                pm = patterns.stripes(w, h, u=along_px + part.get("pattern_offset", 0) * S,
                                      period=pat.get("period", 0.07) * S * scale,
                                      thickness=pat.get("thickness", 0.4), warp=pat.get("warp", 0.3),
                                      breakup=pat.get("breakup", 0.3), taper=pat.get("taper", 0.6),
                                      fork=pat.get("fork", 0.25), seed=pseed + 1)
                # stripes fade out on the belly / toward the part's lower edge if requested
                if "fade_below" in pat:
                    pm *= 1 - smoothstep(pat["fade_below"] - 0.2, pat["fade_below"] + 0.2, vn)
            elif ptype == "spots":
                pm = patterns.spots(w, h, size=pat.get("size", 0.03) * S * scale, rosette=pat.get("rosette", False),
                                    seed=pseed + 1)
            elif ptype == "scales":
                sh_, ed = patterns.scales(w, h, size=pat.get("size", 0.02) * S * scale, seed=pseed + 1)
                pm = ed * pat.get("strength", 0.5)
                col = col * (1 - pat.get("relief", 0.25) + pat.get("relief", 0.25) * sh_[..., None] * 1.6)
            else:
                raise ValidationError(f"Unknown material pattern '{ptype}'")
            col = patterns.colorize(pm * part.get("pattern_strength", 1.0), col, pat.get("color", "#111111"))
        if part.get("emerge"):  # limb grows out of the body: fade in from its first point
            m = m * smoothstep(0.0, float(part["emerge"]), u)
        a = m * part.get("opacity", 1.0)
        img = img * (1 - a[..., None]) + col * a[..., None]
        ph = shading.height_from_mask(m, radius=part.get("roundness", None) and part["roundness"] * S)
        hgt = hgt * (1 - m) + ph * part.get("relief", 1.0) * m
        sf = part.get("shade_factor", 1.0)
        if sf != 1.0:
            img = img * (1 - a[..., None] * (1 - sf))
        ang = np.degrees(np.arctan2(*(p1 - p0)[::-1])) + part.get("fur_angle_offset", 0)
        if part.get("fur_angle") is not None:
            ang = part["fur_angle"]
        flow = np.where(m > 0.5, ang, flow)
        furp = mat.get("fur")
        if furp and part.get("fur", True):
            fur_mask = np.maximum(fur_mask * (1 - a), m)
            fur_params = furp
        else:
            fur_mask *= 1 - a
        alpha = np.maximum(alpha, m * part.get("opacity", 1.0))
    # form lighting (combined part heights + overall silhouette roundness)
    union_h = shading.height_from_mask(alpha)
    H = float(lit.get('part_relief', 0.3)) * hgt + (1 - float(lit.get('part_relief', 0.3))) * union_h
    lit_img = shading.shade(img, alpha, azimuth=az, elevation=light_elevation, key_color=key_color,
                            ambient_color=ambient_color, ambient=lit.get("ambient", ambient),
                            wrap=lit.get("wrap", 0.4), depth=lit.get("depth", 0.25) * S, height=H,
                            rim=lit.get("rim", 0.15), specular=lit.get("specular", 0.0),
                            occlusion=lit.get("occlusion", 0.2))
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = lit_img
    out[..., 3] = alpha
    if fur_params and fur_mask.any():
        f = brush.fur(out, fur_mask, flow, density=fur_params.get("density", 0.08),
                      length=fur_params.get("length", 0.025) * S, width=fur_params.get("width", 1.0),
                      lightness=fur_params.get("lightness", 0.12), angle_jitter=fur_params.get("angle_jitter", 14),
                      seed=seed + 99, edge_hairs=fur_params.get("edge_hairs", 0.5))
        keep = fur_mask[..., None] > 0.5
        out[..., :3] = np.where(keep, f[..., :3], out[..., :3])
        outside = alpha < 0.5
        out[..., :3] = np.where(outside[..., None] & (f[..., 3:4] > 0), f[..., :3], out[..., :3])
        out[..., 3] = np.maximum(alpha, f[..., 3] * (cv2.dilate(fur_mask, np.ones((9, 9), np.uint8)) > 0))
    for d in spec.get("details", []):
        _detail(out, d, S, ox, oy, az, seed)
    if facing == "right":
        out = out[:, ::-1].copy()
    return out


def _detail(out: np.ndarray, d: dict[str, Any], S: float, ox: float, oy: float, az: float, seed: int) -> None:
    h, w = out.shape[:2]
    t = d.get("type")
    col = out[..., :3]

    def paint(mask: np.ndarray, color: ColorLike, opacity: float = 1.0) -> None:
        m = mask[..., None] * opacity
        col[:] = col * (1 - m) + rgb(color) * m

    if t == "eye":
        cx, cy = ox + d["center"][0] * S, oy + d["center"][1] * S
        r = d["radius"] * S
        sq = d.get("squash", 0.75)
        ang = d.get("angle", 0)
        paint(shapes.ellipse(w, h, cx, cy, r * 1.25, r * 1.25 * sq, ang, feather=0.6), d.get("rim", "#120d0a"))
        iris = shapes.ellipse(w, h, cx, cy, r, r * sq, ang, feather=0.4)
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        grad = np.clip(1 - np.hypot(xs - cx, ys - cy) / max(r, 1), 0, 1)
        icol = rgb(d.get("iris", "#d39a2a"))
        col[:] = col * (1 - iris[..., None]) + (icol * (0.55 + 0.6 * grad[..., None])) * iris[..., None]
        pr = r * d.get("pupil", 0.42)
        paint(shapes.ellipse(w, h, cx, cy, pr * d.get("pupil_squash", 1.0), pr, ang, feather=0.4), "#050403")
        hx = cx + np.cos(np.radians(az)) * r * 0.35
        paint(shapes.ellipse(w, h, hx, cy - r * 0.3, r * 0.22, r * 0.18, feather=0.5), "#ffffff", 0.9)
    elif t == "ellipse":
        cx, cy = ox + d["center"][0] * S, oy + d["center"][1] * S
        rx, ry = d["radii"]
        em = shapes.ellipse(w, h, cx, cy, rx * S, ry * S, d.get("angle", 0), feather=d.get("feather", 0.8))
        paint(em, d["color"], d.get("opacity", 1.0))
        if d.get("extend_alpha"):
            out[..., 3] = np.maximum(out[..., 3], em * d.get("opacity", 1.0))
    elif t == "polygon":
        pts = [(ox + x * S, oy + y * S) for x, y in d["points"]]
        paint(shapes.polygon(w, h, pts, feather=d.get("feather", 0.8), smooth=d.get("smooth", True)), d["color"],
              d.get("opacity", 1.0))
    elif t == "stroke":
        pts = [(ox + x * S, oy + y * S) for x, y in d["points"]]
        layer_ = np.zeros((h, w, 4), np.float32)
        brush.stroke(layer_, pts, d["color"], size=d.get("size", 0.01) * S, hardness=d.get("hardness", 0.6),
                     size_end=d.get("size_end", d.get("size", 0.01)) * S, opacity=d.get("opacity", 1.0))
        a = layer_[..., 3:4]
        col[:] = col * (1 - a) + layer_[..., :3] * a
        if d.get("extend_alpha"):
            out[..., 3] = np.maximum(out[..., 3], layer_[..., 3])
    elif t == "eyespots":
        rng = np.random.default_rng(seed + 7)
        for c in d["centers"]:
            r = d.get("radius", 0.03) * S * rng.uniform(0.85, 1.1)
            spot = patterns.eyespot(r, d.get("colors", ["#0b1d4a", "#1d5fa8", "#22a08a", "#c49a2a", "#6f8a2a"]))
            sh_, sw_ = spot.shape[:2]
            x0, y0 = int(ox + c[0] * S - sw_ / 2), int(oy + c[1] * S - sh_ / 2)
            xa, ya, xb, yb = max(0, x0), max(0, y0), min(w, x0 + sw_), min(h, y0 + sh_)
            if xb > xa and yb > ya:
                sp = spot[ya - y0:yb - y0, xa - x0:xb - x0]
                a = sp[..., 3:4] * out[ya:yb, xa:xb, 3:4]
                col[ya:yb, xa:xb] = col[ya:yb, xa:xb] * (1 - a) + sp[..., :3] * a
    else:
        raise ValidationError(f"Unknown detail type '{t}'", details={"types": DETAIL_TYPES})


def place_figure(fig: np.ndarray, width: int, height: int, *, x: float, ground_y: float, spec_height: float
                 ) -> tuple[np.ndarray, tuple[int, int]]:
    """Put a rendered figure on a full canvas: ``x`` = left edge of the figure box, ``ground_y`` = box bottom.
    Returns (canvas RGBA, (x0, y0) of the image's top-left)."""
    from .canvas import place

    pad = int(spec_height * 0.06) + 4
    x0 = int(round(x)) - pad
    y0 = int(round(ground_y - spec_height)) - pad
    return place(fig, width, height, x0, y0), (x0, y0)
