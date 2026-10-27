"""Environment builders: sky, sun, clouds, mountains, ground, ocean, forest, light rays and haze.

Each builder returns a full-canvas float RGBA layer so a pipeline can stack them as separate, named,
editable layers (back to front), exactly like a matte painter works in Photoshop.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from . import brush, patterns, shading, shapes
from .canvas import ColorLike, blank, layer, mix, ramp, rgb, smoothstep
from .noise import fbm, perspective_coords, sample_tiled, tileable_fbm, value_noise

# ----- sky ------------------------------------------------------------------------------------------

def sky(width: int, height: int, *, horizon_y: float, colors: Sequence[ColorLike] = ("#2f5d9c", "#7fa9d6", "#e8eef2"),
        positions: Sequence[float] | None = None, sun: Sequence[float] | None = None,
        sun_color: ColorLike = "#fff1c9", sun_glow: float = 0.5, glow_radius: float = 0.35) -> np.ndarray:
    """Vertical sky gradient (zenith -> horizon) plus an optional warm glow around the sun position."""
    yy = np.linspace(0, 1, height, dtype=np.float32)[:, None] * np.ones((1, width), np.float32)
    t = np.clip(yy * height / max(horizon_y, 1), 0, 1)
    img = ramp(t ** 1.2, colors, positions)
    if sun is not None:
        sx, sy = sun
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        d = np.hypot(xs - sx, (ys - sy) * 1.3) / (max(width, height) * glow_radius)
        glow = np.exp(-d * d * 2.5) * sun_glow
        img = img + (rgb(sun_color) - img) * glow[..., None]
    return layer(img, 1.0)


def sun_disc(width: int, height: int, *, x: float, y: float, radius: float = 22.0, color: ColorLike = "#fff7e0",
             halo: float = 3.0) -> np.ndarray:
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    d = np.hypot(xs - x, ys - y)
    core = smoothstep(radius + 1.5, radius - 1.5, d)
    halo_a = np.exp(-((d / (radius * halo)) ** 2)) * 0.6
    return layer(np.broadcast_to(rgb(color), (height, width, 3)).copy(), np.clip(core + halo_a, 0, 1))


def clouds(width: int, height: int, *, top: float, bottom: float, coverage: float = 0.45, period: float = 260.0,
           color: ColorLike = "#ffffff", shadow: ColorLike = "#8a9bb5", light_from: Sequence[float] | None = None,
           softness: float = 0.12, stretch: float = 3.0, seed: int = 0) -> np.ndarray:
    """Cumulus/stratus band between rows ``top`` and ``bottom`` (perspective: flatter near the bottom).
    ``light_from`` = (x, y) of the sun: cloud sides facing it are lit, the others take the shadow colour."""
    h = max(int(bottom - top), 4)
    sw = int(width / stretch) + 2
    n = fbm(sw, h, period / stretch, 6, seed=seed)
    n = cv2.resize(n, (width, h), interpolation=cv2.INTER_CUBIC)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    fade = smoothstep(0, 0.15, yy) * smoothstep(1.0, 0.6, yy)
    dens = smoothstep(1 - coverage, 1 - coverage + softness, n * fade)
    # shading: sample the density field toward the light; denser toward the light -> shadowed side
    lx, ly = (light_from if light_from is not None else (width / 2, top - 200))
    ang = np.arctan2(ly - (top + h / 2), lx - width / 2)
    shift = np.float32([[1, 0, -np.cos(ang) * 10], [0, 1, -np.sin(ang) * 10]])
    toward = cv2.warpAffine(n * fade, shift, (width, h), borderMode=cv2.BORDER_REFLECT)
    lit = np.clip(0.55 + (n * fade - toward) * 4, 0, 1)
    col = mix(np.broadcast_to(rgb(shadow), (h, width, 3)), np.broadcast_to(rgb(color), (h, width, 3)), lit)
    out = blank(width, height)
    y0 = int(top)
    y1 = min(height, y0 + h)
    out[max(0, y0):y1, :, :3] = col[max(0, -y0):y1 - y0]
    out[max(0, y0):y1, :, 3] = dens[max(0, -y0):y1 - y0]
    return out


# ----- land -----------------------------------------------------------------------------------------

def mountains(width: int, height: int, *, base_y: float, peak: float, roughness: float = 0.55,
              color: ColorLike = "#4a5d73", light: ColorLike = "#8ea3b8", light_azimuth: float = 180.0,
              snow: float = 0.0, seed: int = 0) -> np.ndarray:
    """Mountain range silhouette with ridge shading. ``peak`` = max height above ``base_y`` in px."""
    rng = np.random.default_rng(seed)
    xs = np.arange(width, dtype=np.float32)
    prof = np.zeros(width, np.float32)
    amp, per = 1.0, width / 2.5
    for _ in range(7):
        ph = rng.uniform(0, 1000)
        knots = rng.random(int(width / per) + 4)
        prof += amp * np.interp(xs / per + ph % 1, np.arange(len(knots)), knots)
        amp *= roughness
        per /= 2.1
    prof = (prof - prof.min()) / max(prof.max() - prof.min(), 1e-6)
    top = base_y - peak * prof
    ys = np.arange(height, dtype=np.float32)[:, None]
    alpha = smoothstep(-0.8, 0.8, ys - top[None, :])
    alpha[ys[:, 0] > base_y + 2] = 1.0
    slope = np.gradient(top)
    face = np.clip(-slope * np.cos(np.radians(light_azimuth)) * 0.8 + 0.5, 0, 1)
    tex = fbm(width, height, 40, 5, seed=seed + 1)
    shade_ = np.clip(face[None, :] * 0.7 + tex * 0.3, 0, 1)
    img = mix(np.broadcast_to(rgb(color), (height, width, 3)), np.broadcast_to(rgb(light), (height, width, 3)),
              shade_)
    if snow > 0:
        cap = smoothstep(0.0, 0.25, (top[None, :] + peak * snow - ys) / max(peak, 1)) * (tex > 0.4)
        img = mix(img, np.broadcast_to(rgb("#f2f5f8"), img.shape), cap * 0.9)
    return layer(img, alpha)


def ground(width: int, height: int, *, horizon_y: float, near: ColorLike = "#4b3a24", far: ColorLike = "#7d7458",
           texture: float = 0.35, period: float = 1.2, detail_colors: Sequence[ColorLike] | None = None,
           seed: int = 0) -> np.ndarray:
    """Ground plane below the horizon with perspective-correct texture (detail shrinks with distance)."""
    X, Z, valid = perspective_coords(width, height, horizon_y)
    tex = tileable_fbm(256, 64, 6, seed=seed)
    k = 256 / max(period, 1e-3)
    n = sample_tiled(tex, X * k, Z * k)
    depth = np.clip(1 - np.log1p(Z) / np.log1p(Z[valid].max() if valid.any() else 1), 0, 1)
    base = mix(np.broadcast_to(rgb(far), (height, width, 3)), np.broadcast_to(rgb(near), (height, width, 3)),
               depth ** 0.7)
    if detail_colors:
        base = mix(base, ramp(n, detail_colors), 0.6 * texture)
    else:
        base = base * (1 - texture / 2 + texture * n)[..., None]
    # distant texture averages out
    fade = smoothstep(0, 0.35, depth)
    base = mix(mix(np.broadcast_to(rgb(far), base.shape), base, 0.4), base, fade)
    return layer(base, valid.astype(np.float32))


# ----- water ----------------------------------------------------------------------------------------

def ocean(width: int, height: int, *, horizon_y: float, deep: ColorLike = "#0d3a52", shallow: ColorLike = "#2f7a8c",
          sky_color: ColorLike = "#a9c7de", horizon_color: ColorLike | None = None, sun_x: float | None = None,
          sun_color: ColorLike = "#fff2cc", glitter: float = 0.8, wave_size: float = 0.35, choppiness: float = 0.5,
          foam: float = 0.0, seed: int = 0) -> np.ndarray:
    """Open water from the horizon to the camera: perspective waves, Fresnel sky reflection (bright and
    smooth at the horizon, darker and transparent up close), and a sun-glitter path below ``sun_x``."""
    X, Z, valid = perspective_coords(width, height, horizon_y, camera_height=1.0)
    size = 512
    tex = tileable_fbm(size, size / 6, 6, seed=seed)
    tex2 = tileable_fbm(size, size / 9, 6, seed=seed + 3)
    swell = tileable_fbm(size, size / 2, 3, seed=seed + 7)
    k = size / max(wave_size * 8, 1e-3)
    u, v = X * k * 0.5, Z * k * 1.6  # waves stretched sideways
    # two wave trains crossing at an angle + long swell: breaks up regular banding
    hgt = (sample_tiled(tex, u, v) * 0.6 + sample_tiled(tex2, u * 0.8 + v * 0.35, v * 0.9 - u * 0.25) * 0.4) \
        * choppiness + sample_tiled(swell, u * 0.3, v * 0.3) * (1 - choppiness)
    # slope (screen-space): approximates wave normals
    gy = cv2.Sobel(hgt, cv2.CV_32F, 0, 1, ksize=3)
    gx = cv2.Sobel(hgt, cv2.CV_32F, 1, 0, ksize=3)
    zmax = float(Z[valid].max()) if valid.any() else 1.0
    depth = np.clip(np.log1p(Z) / np.log1p(zmax), 0, 1)  # 0 near camera, 1 at the horizon
    detail = np.clip(1 - depth ** 3, 0, 1)  # far waves average out
    fresnel = np.clip(0.15 + 0.85 * depth ** 2.2 - gy * 0.8 * detail, 0, 1)
    water = mix(np.broadcast_to(rgb(deep), (height, width, 3)), np.broadcast_to(rgb(shallow), (height, width, 3)),
                np.clip(hgt * detail * 0.8, 0, 1))
    refl_col = mix(np.broadcast_to(rgb(sky_color), water.shape),
                   np.broadcast_to(rgb(horizon_color or sky_color), water.shape), depth[..., None] ** 4)
    img = mix(water, refl_col, fresnel)
    # crest highlights / troughs
    img = img * (1 + (hgt - 0.5)[..., None] * 0.35 * detail[..., None])
    if sun_x is not None and glitter > 0:
        spread = (0.02 + 0.22 * (1 - depth)) * width  # glitter path widens toward the camera
        path = np.exp(-((np.arange(width, dtype=np.float32)[None, :] - sun_x) / spread) ** 2)
        sparkle = smoothstep(0.55, 0.95, np.clip(-gy * 3 + hgt * 0.6 + gx * 0.2, 0, 1))
        sparkle = sparkle * (0.35 + 0.65 * value_noise(width, height, 3, seed + 3))
        g = np.clip(path * (sparkle * 1.6 + depth ** 6 * 0.6) * glitter, 0, 1)
        img = img + rgb(sun_color) * g[..., None]
    if foam > 0:
        f = smoothstep(1 - foam * 0.25, 1.0, hgt) * detail
        img = mix(img, np.broadcast_to(rgb("#eef4f6"), img.shape), f * 0.8)
    return layer(np.clip(img, 0, 1), valid.astype(np.float32))


# ----- vegetation -----------------------------------------------------------------------------------

def tree(width: int, height: int, *, x: float, ground_y: float, trunk_width: float, top_y: float = -50,
         bark_color: ColorLike = "#4a3a2c", bark_light: ColorLike = "#8a735a", light_azimuth: float = 180.0,
         lean: float = 0.0, branches: int = 3, moss: float = 0.0, moss_color: ColorLike = "#5b6b2a",
         seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """One trunk: tapered, slightly irregular outline, root flare, fissured bark, cylindrical side light,
    optional moss on the shaded side, and a few branches. Returns (rgb, alpha)."""
    rng = np.random.default_rng(seed)
    p0 = np.array([x, ground_y + trunk_width * 0.1], np.float32)
    p1 = np.array([x + lean * (ground_y - top_y), top_y], np.float32)
    n_seg = 6
    pts = [p0 + (p1 - p0) * t + np.array([rng.normal(0, trunk_width * 0.06), 0]) * (0 < t < 1)
           for t in np.linspace(0, 1, n_seg)]
    radii = [trunk_width / 2 * (1 - 0.35 * t) for t in np.linspace(0, 1, n_seg)]
    alpha = shapes.bent_capsule(width, height, pts, radii)
    # root flare: a widening wedge at the base with a couple of roots
    fw = trunk_width * 0.68
    flare = [(x - fw, ground_y + trunk_width * 0.05), (x - trunk_width * 0.45, ground_y - trunk_width * 0.45),
             (x + trunk_width * 0.45, ground_y - trunk_width * 0.45), (x + fw, ground_y + trunk_width * 0.05),
             (x, ground_y + trunk_width * 0.1)]
    alpha = np.maximum(alpha, shapes.polygon(width, height, flare, smooth=True))
    for _ in range(branches):
        t = rng.uniform(0.05, 0.5)
        by = top_y + (ground_y - top_y) * t
        bx = p1[0] + (p0[0] - p1[0]) * t
        side = rng.choice([-1, 1])
        ln = trunk_width * rng.uniform(2, 5)
        bpts = [(bx, by), (bx + side * ln * 0.6, by - ln * 0.35), (bx + side * ln, by - ln * 0.8)]
        alpha = np.maximum(alpha, shapes.bent_capsule(width, height, bpts, [trunk_width * 0.16, trunk_width * 0.05]))
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]
    tt = np.clip((ys - top_y) / max(ground_y - top_y, 1), 0, 1)
    cx = p1[0] + (p0[0] - p1[0]) * tt
    half = trunk_width / 2 * (1 - 0.35 * (1 - tt)) + 1
    across = np.clip((xs - cx) / half, -1, 1)  # -1 left edge .. 1 right edge
    nx = across
    nz = np.sqrt(np.clip(1 - across ** 2, 0, 1))
    lx = np.cos(np.radians(light_azimuth))
    lz = max(np.sin(np.radians(light_azimuth)), 0.15)
    lam = np.clip((nx * lx + nz * lz + 0.25) / 1.25, 0, 1)
    b = patterns.bark(width, height, period=max(trunk_width / 4, 3), seed=seed)
    blotch = fbm(width, height, trunk_width * 1.5, 3, seed=seed + 3)
    shade_ = lam * (0.45 + 0.55 * b) * (0.8 + 0.4 * blotch)
    img = mix(np.broadcast_to(rgb(bark_color), (height, width, 3)) * 0.5,
              np.broadcast_to(rgb(bark_light), (height, width, 3)), np.clip(shade_, 0, 1))
    if moss > 0:
        mm = smoothstep(0.6, 0.7, fbm(width, height, trunk_width * 0.6, 5, seed=seed + 9)) * \
            np.clip(-nx * np.sign(lx) * 0.8 + 0.3, 0, 1) * moss * 2
        img = mix(img, np.broadcast_to(rgb(moss_color), img.shape) * (0.6 + 0.6 * b[..., None]), np.clip(mm, 0, 1))
    return img, alpha


def foliage(width: int, height: int, *, centers: Sequence[Sequence[float]], radius: float,
            colors: Sequence[ColorLike] = ("#13240f", "#2a4a1c", "#4f7a2a", "#9dbb57"), light_azimuth: float = 180.0,
            light_elevation: float = 45.0, leaf_size: float = 5.0, density: float = 1.0, sub_clumps: int = 6,
            squash: float = 0.8, seed: int = 0) -> np.ndarray:
    """Leafy masses painted with a scatter-leaf brush: each clump is a few rounded sub-clumps filled with a
    dark core and covered by thousands of small leaf dabs. Each dab is lit as a point on a sphere
    (``light_azimuth``/``light_elevation``), so clumps read as volumes with lit tops and dark undersides."""
    rng = np.random.default_rng(seed)
    img = np.zeros((height, width, 3), np.uint8)
    cov = np.zeros((height, width), np.uint8)
    L = shading.light_vector(light_azimuth, light_elevation)
    cols = np.stack([rgb(c) for c in colors])
    pos = np.linspace(0, 1, len(cols))
    dark = tuple(int(v) for v in (cols[0] * 255 * 0.8))
    subs = []
    for (cx, cy) in centers:
        for _ in range(max(1, int(sub_clumps))):
            r = radius * rng.uniform(0.35, 0.7)
            subs.append((cx + rng.normal(0, radius * 0.5), cy + rng.normal(0, radius * 0.35 * squash), r))
    subs.sort(key=lambda c: c[1])  # higher clumps first; lower (nearer) ones overlap them
    for (sx, sy, r) in subs:
        cv2.ellipse(cov, (int(sx * 16), int(sy * 16)), (int(r * 0.8 * 16), int(r * 0.8 * squash * 16)), 0, 0, 360,
                    255, -1, cv2.LINE_AA, 4)
        cv2.ellipse(img, (int(sx * 16), int(sy * 16)), (int(r * 0.8 * 16), int(r * 0.8 * squash * 16)), 0, 0, 360,
                    dark, -1, cv2.LINE_AA, 4)
        n = int(density * 1.6 * (r / max(leaf_size, 1)) ** 2) + 8
        ang = rng.uniform(0, 2 * np.pi, n)
        rad = np.sqrt(rng.random(n))
        px, py = np.cos(ang) * rad, np.sin(ang) * rad
        pz = np.sqrt(np.clip(1 - px * px - py * py, 0, 1))
        order = np.argsort(pz)
        lum = np.clip(((px * L[0] + py * L[1] + pz * L[2]) + 0.35) / 1.35, 0, 1)
        lum = lum * (0.75 + 0.25 * pz) * rng.uniform(0.75, 1.15, n)
        lum = np.clip(lum + rng.normal(0, 0.06, n), 0, 1)
        for i in order:
            c = np.array([np.interp(lum[i], pos, cols[:, k]) for k in range(3)]) * 255
            c = c * rng.uniform(0.9, 1.1, 3)
            ls = leaf_size * rng.uniform(0.6, 1.35)
            x, y = sx + px[i] * r, sy + py[i] * r * squash
            a = float(rng.uniform(0, 180))
            ax = (int(ls * 16), int(ls * 0.55 * 16))
            cv2.ellipse(img, (int(x * 16), int(y * 16)), ax, a, 0, 360, np.clip(c, 0, 255).tolist(), -1,
                        cv2.LINE_AA, 4)
            cv2.ellipse(cov, (int(x * 16), int(y * 16)), ax, a, 0, 360, 255, -1, cv2.LINE_AA, 4)
    a = cov.astype(np.float32) / 255
    out = img.astype(np.float32) / 255
    out = np.where(a[..., None] > 0, out / np.maximum(a[..., None], 1e-3), 0)
    return layer(np.clip(out, 0, 1), a)


def forest_wall(width: int, height: int, *, horizon_y: float, top: float, color: ColorLike = "#5f6f58",
                fog_color: ColorLike = "#c9cfb2", fog: float = 0.6, trunks: int = 60, seed: int = 0) -> np.ndarray:
    """The far forest: a hazy mass of thin trunks and canopy that hides the horizon line."""
    rng = np.random.default_rng(seed)
    a = np.zeros((height, width), np.float32)
    canopy_line = top + (horizon_y - top) * 0.35 * fbm(width, 1, 90, 4, seed=seed)[0] + \
        (horizon_y - top) * 0.2 * value_noise(width, 1, 25, seed + 1)[0]
    ys = np.arange(height, dtype=np.float32)[:, None]
    a = np.maximum(a, smoothstep(-1.5, 1.5, ys - canopy_line[None, :]) * (ys < horizon_y + 40))
    for x in rng.uniform(0, width, trunks):
        w_ = rng.uniform(2, 7)
        a = np.maximum(a, shapes.capsule(width, height, (x, horizon_y + 30), (x + rng.normal(0, 4), top), w_, w_ * 0.6))
    a *= smoothstep(horizon_y + 60, horizon_y + 20, ys)
    tex = fbm(width, height, 30, 4, seed=seed + 2)
    img = np.broadcast_to(rgb(color), (height, width, 3)) * (0.75 + 0.5 * tex[..., None])
    img = mix(img, np.broadcast_to(rgb(fog_color), img.shape), fog)
    return layer(np.clip(img, 0, 1), np.clip(a, 0, 1))


def forest(width: int, height: int, *, horizon_y: float, depth_layers: int = 4, trees_per_layer: int = 9,
           trunk_width: float = 60.0, bark_color: ColorLike = "#3d2f24", bark_light: ColorLike = "#8b7356",
           foliage_colors: Sequence[ColorLike] = ("#13240f", "#2a4a1c", "#4f7a2a", "#9dbb57"),
           fog_color: ColorLike = "#b7c7a8", fog: float = 0.75, light_azimuth: float = 200.0,
           canopy: bool = True, undergrowth: float = 1.0, seed: int = 0) -> list[tuple[str, np.ndarray]]:
    """Layered forest (far -> near). Distant layers are smaller, paler and hazier (atmospheric
    perspective); near layers are large, dark and contrasty. Returns [(layer name, RGBA), ...]."""
    rng = np.random.default_rng(seed)
    wall = forest_wall(width, height, horizon_y=horizon_y, top=horizon_y - height * 0.45, fog_color=fog_color,
                       fog=fog * 0.7, seed=seed)
    band = foliage(width, height, centers=[(float(x), horizon_y + float(rng.uniform(-6, 10)))
                                           for x in np.linspace(-20, width + 20, int(width / 45))],
                   radius=height * 0.08, colors=foliage_colors, light_azimuth=light_azimuth, leaf_size=2.0,
                   density=0.8, squash=0.5, sub_clumps=4, seed=seed + 77)
    band[..., :3] = mix(band[..., :3], np.broadcast_to(rgb(fog_color), band[..., :3].shape), fog * 0.8)
    wall = _over_rgb(wall, band[..., :3], band[..., 3])
    out = [("far wall", wall)]
    for li in range(depth_layers):
        t = (li + 1) / depth_layers  # 0.25 far .. 1.0 near
        scale = 0.25 + 0.75 * t ** 1.4
        gy = horizon_y + (height - horizon_y) * (0.04 + 0.45 * t ** 2)
        tw = trunk_width * scale
        lay = blank(width, height)
        n = max(2, int(trees_per_layer * (1.5 - t * 0.7)))
        xs = np.sort(rng.uniform(-tw, width + tw, n))
        for k, x in enumerate(xs):
            img, a = tree(width, height, x=float(x), ground_y=float(gy + rng.normal(0, 6 * scale)),
                          trunk_width=float(tw * rng.uniform(0.7, 1.3)), top_y=-40,
                          bark_color=bark_color, bark_light=bark_light, light_azimuth=light_azimuth,
                          lean=float(rng.normal(0, 0.02)), branches=int(rng.integers(1, 4)),
                          seed=seed * 100 + li * 17 + k)
            lay = _over_rgb(lay, img, a)
        if canopy:
            centers = [(float(x), float(rng.uniform(-0.08, 0.1) * height)) for x in
                       np.linspace(-80, width + 80, int(4 + 5 * (1 - t)))]
            leaves = foliage(width, height, centers=centers, radius=height * (0.1 + 0.12 * scale),
                             colors=foliage_colors, light_azimuth=light_azimuth, leaf_size=2 + 5 * scale,
                             seed=seed * 10 + li)
            lay = _over_rgb(lay, leaves[..., :3], leaves[..., 3])
        if undergrowth > 0:
            bushes = [(float(x), float(gy - rng.uniform(5, 25) * scale))
                      for x in rng.uniform(0, width, int((5 + 5 * t) * undergrowth))]
            under = foliage(width, height, centers=bushes, radius=55 * scale + 8, colors=foliage_colors,
                            light_azimuth=light_azimuth, leaf_size=1.5 + 4 * scale, density=0.9, squash=0.6,
                            sub_clumps=4, seed=seed * 20 + li)
            lay = _over_rgb(lay, under[..., :3], under[..., 3])
        haze = fog * (1 - t) ** 1.1
        lay[..., :3] = mix(lay[..., :3], np.broadcast_to(rgb(fog_color), lay[..., :3].shape), haze)
        out.append((f"depth {li + 1} ({'far' if li == 0 else 'near' if li == depth_layers - 1 else 'mid'})", lay))
    return out


def _over_rgb(dst: np.ndarray, rgb_img: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    a = alpha[..., None]
    da = dst[..., 3:4]
    oa = a + da * (1 - a)
    dst[..., :3] = (rgb_img * a + dst[..., :3] * da * (1 - a)) / np.maximum(oa, 1e-6)
    dst[..., 3:4] = oa
    return dst


def grass(width: int, height: int, **kw) -> np.ndarray:
    """Grass blades (see :func:`image_studio.paint.brush.grass`)."""
    return brush.grass(width, height, **kw)


# ----- light & air ----------------------------------------------------------------------------------

def light_rays(width: int, height: int, *, origin: Sequence[float], color: ColorLike = "#fff0c8", count: int = 9,
               spread: float = 50.0, angle: float = 70.0, length: float = 1.4, intensity: float = 0.35,
               softness: float = 18.0, seed: int = 0) -> np.ndarray:
    """Crepuscular rays (god rays) fanning from ``origin`` toward ``angle`` (deg, 90 = straight down).
    Use as a screen/linear-dodge layer."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    dx, dy = xs - origin[0], ys - origin[1]
    ang = np.degrees(np.arctan2(dy, dx))
    dist = np.hypot(dx, dy) / max(width, height)
    m = np.zeros((height, width), np.float32)
    for _ in range(count):
        a0 = angle + rng.uniform(-spread / 2, spread / 2)
        w = rng.uniform(0.6, 2.2)
        m += np.exp(-((ang - a0) / w) ** 2) * rng.uniform(0.4, 1.0)
    m *= np.exp(-dist / max(length, 1e-3) * 1.5) * smoothstep(0, 0.05, dist)
    m = cv2.GaussianBlur(m, (0, 0), softness)
    m *= 0.6 + 0.4 * fbm(width, height, 120, 3, seed=seed + 1)
    return layer(np.broadcast_to(rgb(color), (height, width, 3)).copy(), np.clip(m * intensity, 0, 1))


def haze(width: int, height: int, *, horizon_y: float, color: ColorLike = "#cfd8de", strength: float = 0.5,
         band: float = 0.18, noise: float = 0.3, seed: int = 0) -> np.ndarray:
    """Atmospheric haze/mist concentrated around the horizon line."""
    yy = np.arange(height, dtype=np.float32)[:, None]
    d = np.abs(yy - horizon_y) / (band * height)
    a = np.exp(-d * d) * strength
    a = a * (1 - noise + noise * fbm(width, height, 200, 4, seed=seed))
    return layer(np.broadcast_to(rgb(color), (height, width, 3)).copy(), np.clip(a, 0, 1))


def dapples(width: int, height: int, *, size: float = 60.0, coverage: float = 0.35, color: ColorLike = "#ffd99a",
            softness: float = 0.2, stretch: float = 1.0, region: Sequence[float] | None = None,
            seed: int = 0) -> np.ndarray:
    """Sun flecks / dappled light through a canopy: soft irregular patches (use soft_light/screen, often
    clipped to a subject or masked to the ground). ``stretch`` > 1 flattens them horizontally (light pools on
    the ground seen in perspective); ``region`` = [x, y, w, h] limits them."""
    sw = max(2, int(width / max(stretch, 1e-3)))
    n = cv2.resize(fbm(sw, height, size / max(stretch, 1e-3) if stretch < 1 else size, 4, seed=seed),
                   (width, height), interpolation=cv2.INTER_CUBIC)
    a = smoothstep(1 - coverage, 1 - coverage + softness, n)
    if region is not None:
        x, y, w, h = region
        ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
        inside = smoothstep(0, 40, np.minimum.reduce([xs - x, x + w - xs, ys - y, y + h - ys]))
        a = a * inside
    return layer(np.broadcast_to(rgb(color), (height, width, 3)).copy(), a)
