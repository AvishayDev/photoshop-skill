"""Color and tone adjustments on float RGB (0..1).

The same functions back destructive edits (``adjust_colors`` on a layer) and
non-destructive adjustment layers, so results are identical either way.
Each adjustment declares its parameters, defaults and valid ranges; inputs are
validated before any pixels are touched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..errors import ValidationError
from .color import hsv_to_rgb, lab_to_rgb, luminance, parse_color, rgb_to_hsv, rgb_to_lab


@dataclass
class Param:
    default: Any
    lo: float | None = None
    hi: float | None = None
    doc: str = ""
    kind: str = "number"  # number | bool | color | points | channel | dict


@dataclass
class AdjustmentSpec:
    name: str
    fn: Callable[..., np.ndarray]
    params: dict[str, Param] = field(default_factory=dict)
    doc: str = ""


def _curve_lut(points: list[list[float]]) -> np.ndarray:
    """Monotone cubic (Fritsch-Carlson) curve through 0..255 control points -> 256 LUT in 0..1."""
    pts = sorted((float(x), float(y)) for x, y in points)
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < 255:
        pts.append((255.0, pts[-1][1]))
    xs = np.array([p[0] for p in pts])
    ys = np.array([p[1] for p in pts])
    if np.any(np.diff(xs) <= 0):
        raise ValidationError("Curve points must have distinct x values")
    d = np.diff(ys) / np.diff(xs)
    m = np.zeros_like(ys)
    m[1:-1] = np.where(d[:-1] * d[1:] > 0, (d[:-1] + d[1:]) / 2, 0)
    m[0], m[-1] = d[0], d[-1]
    for i in range(len(d)):
        if d[i] == 0:
            m[i] = m[i + 1] = 0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                t = 3 / np.sqrt(s)
                m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    x = np.arange(256, dtype=np.float64)
    idx = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, len(xs) - 2)
    h = xs[idx + 1] - xs[idx]
    t = (x - xs[idx]) / h
    h00, h10 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t
    h01, h11 = -2 * t**3 + 3 * t**2, t**3 - t**2
    y = h00 * ys[idx] + h10 * h * m[idx] + h01 * ys[idx + 1] + h11 * h * m[idx + 1]
    return np.clip(y / 255.0, 0, 1).astype(np.float32)


def _apply_lut(ch: np.ndarray, lut: np.ndarray) -> np.ndarray:
    pos = np.clip(ch, 0, 1) * 255.0
    lo = np.floor(pos).astype(np.int32)
    hi = np.minimum(lo + 1, 255)
    f = pos - lo
    return lut[lo] * (1 - f) + lut[hi] * f


def brightness_contrast(rgb, brightness=0.0, contrast=0.0):
    """brightness/contrast in -1..1 (GIMP-style)."""
    out = rgb + brightness
    k = np.tan((contrast + 1) * np.pi / 4)
    return (out - 0.5) * k + 0.5


def levels(rgb, in_black=0.0, in_white=255.0, gamma=1.0, out_black=0.0, out_white=255.0, channel="rgb"):
    if in_white <= in_black:
        raise ValidationError("in_white must be greater than in_black")
    def f(c):
        v = np.clip((c * 255 - in_black) / (in_white - in_black), 0, 1) ** (1.0 / gamma)
        return (out_black + v * (out_white - out_black)) / 255.0
    return _per_channel(rgb, f, channel)


def _per_channel(rgb, f, channel):
    out = rgb.copy()
    idx = {"rgb": [0, 1, 2], "red": [0], "green": [1], "blue": [2]}.get(channel)
    if idx is None:
        raise ValidationError("channel must be one of rgb, red, green, blue")
    for i in idx:
        out[..., i] = f(rgb[..., i])
    return out


def curves(rgb, points=None, red=None, green=None, blue=None):
    """Tone curves; each is a list of [input, output] pairs in 0..255."""
    out = rgb.copy()
    if points:
        lut = _curve_lut(points)
        for i in range(3):
            out[..., i] = _apply_lut(out[..., i], lut)
    for i, pts in enumerate((red, green, blue)):
        if pts:
            out[..., i] = _apply_lut(out[..., i], _curve_lut(pts))
    return out


def hue_saturation(rgb, hue=0.0, saturation=0.0, lightness=0.0, colorize=False):
    """hue in degrees (-180..180); saturation and lightness in -1..1."""
    hsv = rgb_to_hsv(np.clip(rgb, 0, 1))
    if colorize:
        hsv[..., 0] = (hue % 360) / 360.0
        hsv[..., 1] = np.clip(0.5 + saturation * 0.5, 0, 1)
    else:
        hsv[..., 0] = hsv[..., 0] + hue / 360.0
        hsv[..., 1] = np.clip(hsv[..., 1] * (1 + saturation), 0, 1)
    out = hsv_to_rgb(hsv)
    if lightness > 0:
        out = out + (1 - out) * lightness
    elif lightness < 0:
        out = out * (1 + lightness)
    return out


def color_balance(rgb, shadows=(0, 0, 0), midtones=(0, 0, 0), highlights=(0, 0, 0), preserve_luminosity=True):
    """Each tone range takes [cyan-red, magenta-green, yellow-blue] shifts in -1..1."""
    lum = luminance(np.clip(rgb, 0, 1))[..., None]
    w_sh = np.clip(1 - lum * 3.3, 0, 1)
    w_hi = np.clip((lum - 0.7) * 3.3, 0, 1)
    w_mid = np.clip(1 - w_sh - w_hi, 0, 1)
    out = rgb + w_sh * np.array(shadows, np.float32) * 0.3 + w_mid * np.array(midtones, np.float32) * 0.3 \
        + w_hi * np.array(highlights, np.float32) * 0.3
    if preserve_luminosity:
        out = out + (lum - luminance(np.clip(out, 0, 1))[..., None])
    return out


def exposure(rgb, ev=0.0, offset=0.0, gamma=1.0):
    """Exposure in stops, applied in linear light."""
    lin = np.clip(rgb, 0, 1) ** 2.2
    lin = np.clip(lin * (2.0 ** ev) + offset, 0, None)
    out = lin ** (1 / 2.2)
    if gamma != 1:
        out = np.clip(out, 0, 1) ** (1 / gamma)
    return out


def vibrance(rgb, amount=0.0):
    """Boost saturation of muted colors more than saturated ones (amount -1..1)."""
    hsv = rgb_to_hsv(np.clip(rgb, 0, 1))
    s = hsv[..., 1]
    hsv[..., 1] = np.clip(s + amount * (1 - s) * s * 1.5 if amount >= 0 else s * (1 + amount), 0, 1)
    return hsv_to_rgb(hsv)


def temperature_tint(rgb, temperature=0.0, tint=0.0):
    """temperature -1 (cool/blue) .. 1 (warm/orange); tint -1 (green) .. 1 (magenta)."""
    lab = rgb_to_lab(np.clip(rgb, 0, 1))
    lab[..., 2] += temperature * 30
    lab[..., 1] += tint * 30
    return lab_to_rgb(lab)


def photo_filter(rgb, color="#ec8a00", density=0.25, preserve_luminosity=True):
    c = np.array(parse_color(color)[:3], np.float32) / 255.0
    out = rgb * (1 - density) + rgb * c * density * 2
    if preserve_luminosity:
        out = out + (luminance(np.clip(rgb, 0, 1)) - luminance(np.clip(out, 0, 1)))[..., None]
    return out


def channel_mixer(rgb, red=(1, 0, 0), green=(0, 1, 0), blue=(0, 0, 1), monochrome=False):
    m = np.array([red, green, blue], np.float32)
    out = rgb @ m.T
    if monochrome:
        out = np.repeat(out[..., :1], 3, axis=-1)
    return out


def black_white(rgb, red=0.3, green=0.59, blue=0.11, tint=None, tint_strength=0.0):
    w = np.array([red, green, blue], np.float32)
    gray = (rgb * w).sum(-1, keepdims=True) / max(float(w.sum()), 1e-6)
    out = np.repeat(gray, 3, axis=-1)
    if tint:
        c = np.array(parse_color(tint)[:3], np.float32) / 255.0
        out = out * (1 - tint_strength) + out * c * tint_strength * 2
    return out


def invert(rgb):
    return 1 - rgb


def posterize(rgb, levels_count=4):
    n = max(2, int(levels_count))
    return np.round(np.clip(rgb, 0, 1) * (n - 1)) / (n - 1)


def threshold(rgb, level=128):
    lum = luminance(np.clip(rgb, 0, 1))
    return np.repeat((lum >= level / 255.0).astype(np.float32)[..., None], 3, axis=-1)


def color_transfer(rgb, src_mean=(50, 0, 0), src_std=(20, 10, 10), dst_mean=(50, 0, 0), dst_std=(20, 10, 10),
                   strength=1.0, preserve_luminance=False):
    """Reinhard-style statistics transfer in CIE Lab (used by match_color)."""
    lab = rgb_to_lab(np.clip(rgb, 0, 1))
    sm, ss = np.array(src_mean, np.float32), np.maximum(np.array(src_std, np.float32), 1e-3)
    dm, ds = np.array(dst_mean, np.float32), np.array(dst_std, np.float32)
    moved = (lab - sm) * (ds / ss) + dm
    if preserve_luminance:
        moved[..., 0] = lab[..., 0]
    lab = lab + (moved - lab) * strength
    return lab_to_rgb(lab)


SPECS: dict[str, AdjustmentSpec] = {
    "brightness_contrast": AdjustmentSpec("brightness_contrast", brightness_contrast, {
        "brightness": Param(0.0, -1, 1), "contrast": Param(0.0, -1, 1)}),
    "levels": AdjustmentSpec("levels", levels, {
        "in_black": Param(0.0, 0, 254), "in_white": Param(255.0, 1, 255), "gamma": Param(1.0, 0.1, 10),
        "out_black": Param(0.0, 0, 255), "out_white": Param(255.0, 0, 255),
        "channel": Param("rgb", kind="channel")}),
    "curves": AdjustmentSpec("curves", curves, {
        "points": Param(None, kind="points"), "red": Param(None, kind="points"),
        "green": Param(None, kind="points"), "blue": Param(None, kind="points")}),
    "hue_saturation": AdjustmentSpec("hue_saturation", hue_saturation, {
        "hue": Param(0.0, -180, 180), "saturation": Param(0.0, -1, 1), "lightness": Param(0.0, -1, 1),
        "colorize": Param(False, kind="bool")}),
    "color_balance": AdjustmentSpec("color_balance", color_balance, {
        "shadows": Param([0, 0, 0], kind="triplet"), "midtones": Param([0, 0, 0], kind="triplet"),
        "highlights": Param([0, 0, 0], kind="triplet"), "preserve_luminosity": Param(True, kind="bool")}),
    "exposure": AdjustmentSpec("exposure", exposure, {
        "ev": Param(0.0, -10, 10), "offset": Param(0.0, -0.5, 0.5), "gamma": Param(1.0, 0.1, 10)}),
    "vibrance": AdjustmentSpec("vibrance", vibrance, {"amount": Param(0.0, -1, 1)}),
    "temperature_tint": AdjustmentSpec("temperature_tint", temperature_tint, {
        "temperature": Param(0.0, -1, 1), "tint": Param(0.0, -1, 1)}),
    "photo_filter": AdjustmentSpec("photo_filter", photo_filter, {
        "color": Param("#ec8a00", kind="color"), "density": Param(0.25, 0, 1),
        "preserve_luminosity": Param(True, kind="bool")}),
    "channel_mixer": AdjustmentSpec("channel_mixer", channel_mixer, {
        "red": Param([1, 0, 0], kind="triplet"), "green": Param([0, 1, 0], kind="triplet"),
        "blue": Param([0, 0, 1], kind="triplet"), "monochrome": Param(False, kind="bool")}),
    "black_white": AdjustmentSpec("black_white", black_white, {
        "red": Param(0.3, -2, 3), "green": Param(0.59, -2, 3), "blue": Param(0.11, -2, 3),
        "tint": Param(None, kind="color"), "tint_strength": Param(0.0, 0, 1)}),
    "invert": AdjustmentSpec("invert", invert, {}),
    "posterize": AdjustmentSpec("posterize", posterize, {"levels_count": Param(4, 2, 255)}),
    "threshold": AdjustmentSpec("threshold", threshold, {"level": Param(128, 0, 255)}),
    "color_transfer": AdjustmentSpec("color_transfer", color_transfer, {
        "src_mean": Param([50, 0, 0], kind="triplet"), "src_std": Param([20, 10, 10], kind="triplet"),
        "dst_mean": Param([50, 0, 0], kind="triplet"), "dst_std": Param([20, 10, 10], kind="triplet"),
        "strength": Param(1.0, 0, 1), "preserve_luminance": Param(False, kind="bool")}),
}


def validate_params(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    spec = SPECS.get(name)
    if spec is None:
        raise ValidationError(f"Unknown adjustment '{name}'", details={"available": sorted(SPECS)})
    params = dict(params or {})
    unknown = set(params) - set(spec.params)
    if unknown:
        raise ValidationError(f"Unknown parameters for {name}: {sorted(unknown)}",
                              details={"accepted": {k: v.default for k, v in spec.params.items()}})
    out: dict[str, Any] = {}
    for key, p in spec.params.items():
        v = params.get(key, p.default)
        if p.kind == "number" and v is not None:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValidationError(f"{name}.{key} must be a number")
            if (p.lo is not None and v < p.lo) or (p.hi is not None and v > p.hi):
                raise ValidationError(f"{name}.{key}={v} is outside the range [{p.lo}, {p.hi}]")
        elif p.kind == "bool":
            v = bool(v)
        elif p.kind == "triplet" and v is not None:
            if not (isinstance(v, (list, tuple)) and len(v) == 3):
                raise ValidationError(f"{name}.{key} must be a list of 3 numbers")
            v = [float(x) for x in v]
        elif p.kind == "points" and v is not None:
            if not (isinstance(v, list) and len(v) >= 2 and all(isinstance(q, (list, tuple)) and len(q) == 2 for q in v)):
                raise ValidationError(f"{name}.{key} must be a list of at least two [input, output] pairs (0..255)")
            if not all(0 <= float(a) <= 255 and 0 <= float(b) <= 255 for a, b in v):
                raise ValidationError(f"{name}.{key} values must be within 0..255")
        elif p.kind == "color" and v is not None:
            parse_color(v)
        elif p.kind == "channel" and v not in ("rgb", "red", "green", "blue"):
            raise ValidationError(f"{name}.{key} must be rgb, red, green or blue")
        out[key] = v
    return out


def apply_adjustment(rgb: np.ndarray, name: str, params: dict[str, Any]) -> np.ndarray:
    clean = validate_params(name, params)
    return np.clip(SPECS[name].fn(rgb.astype(np.float32), **clean), 0, 1).astype(np.float32)
