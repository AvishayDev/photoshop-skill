"""Rendering of parametric layers (text, shapes, fills) and procedural textures."""

from __future__ import annotations

import functools
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..errors import ValidationError
from .color import parse_color
from .layer import FillProps, ShapeProps, TextProps

_FONT_DIRS = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
              Path.home() / ".local/share/fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
              Path.home() / "Library/Fonts", Path("C:/Windows/Fonts")]


@functools.lru_cache(maxsize=1)
def _font_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for d in _FONT_DIRS:
        if d.is_dir():
            for p in d.rglob("*"):
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    idx.setdefault(p.stem.lower().replace(" ", "").replace("-", "").replace("_", ""), str(p))
    return idx


def resolve_font(name: str) -> str | None:
    """Resolve a font family/style name ('DejaVu Sans Bold') or file path to a font file."""
    p = Path(name).expanduser()
    if p.suffix.lower() in (".ttf", ".otf", ".ttc") and p.is_file():
        return str(p)
    if shutil.which("fc-match"):
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip() and Path(out.stdout.strip()).is_file():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    key = name.lower().replace(" ", "").replace("-", "").replace("_", "")
    idx = _font_index()
    if key in idx:
        return idx[key]
    for k, v in idx.items():
        if key in k:
            return v
    for fallback in ("dejavusans", "arial", "liberationsans", "helvetica", "freesans"):
        if fallback in idx:
            return idx[fallback]
    return None


def render_text(props: TextProps) -> tuple[np.ndarray, str | None]:
    """Render text to a tight RGBA array. Returns (pixels, resolved font path)."""
    if not props.text:
        raise ValidationError("Text must not be empty")
    font_path = props.font_path or resolve_font(props.font)
    size = max(1, int(round(props.size)))
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)
    text = props.text
    if props.max_width:
        text = _wrap(text, font, props.max_width)
    color = parse_color(props.color)
    stroke_fill = parse_color(props.stroke_color) if props.stroke_width else None
    spacing = int(size * (props.line_spacing - 1.0)) + 4
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = probe.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=props.align,
                                    stroke_width=props.stroke_width)
    pad = 2 + props.stroke_width
    w, h = bbox[2] - bbox[0] + 2 * pad, bbox[3] - bbox[1] + 2 * pad
    img = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    ImageDraw.Draw(img).multiline_text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=color,
                                       spacing=spacing, align=props.align, stroke_width=props.stroke_width,
                                       stroke_fill=stroke_fill)
    return np.asarray(img).copy(), font_path


def _wrap(text: str, font, max_width: int) -> str:
    lines = []
    for para in text.split("\n"):
        words, cur = para.split(" "), ""
        for wd in words:
            trial = f"{cur} {wd}".strip()
            if font.getlength(trial) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
    return "\n".join(lines)


def render_shape(props: ShapeProps, supersample: int = 4) -> np.ndarray:
    if props.width < 1 or props.height < 1:
        raise ValidationError("Shape width and height must be >= 1")
    ss = supersample
    pad = int(np.ceil(props.stroke_width / 2)) + 1
    W, H = (props.width + 2 * pad) * ss, (props.height + 2 * pad) * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fill = parse_color(props.fill) if props.fill else None
    stroke = parse_color(props.stroke) if props.stroke and props.stroke_width > 0 else None
    sw = int(round(props.stroke_width * ss))
    box = [pad * ss, pad * ss, (pad + props.width) * ss - 1, (pad + props.height) * ss - 1]
    if props.shape == "rectangle":
        d.rectangle(box, fill=fill, outline=stroke, width=sw)
    elif props.shape == "rounded_rectangle":
        d.rounded_rectangle(box, radius=props.corner_radius * ss, fill=fill, outline=stroke, width=sw)
    elif props.shape == "ellipse":
        d.ellipse(box, fill=fill, outline=stroke, width=sw)
    elif props.shape in ("polygon", "line"):
        if not props.points or len(props.points) < 2:
            raise ValidationError("polygon/line shapes need at least 2 points")
        pts = [((x + pad) * ss, (y + pad) * ss) for x, y in props.points]
        if props.shape == "polygon":
            d.polygon(pts, fill=fill, outline=stroke, width=max(sw, 1) if stroke else 0)
        else:
            d.line(pts, fill=stroke or fill, width=max(sw, ss), joint="curve")
    else:
        raise ValidationError(f"Unknown shape '{props.shape}'",
                              hint="Use rectangle, rounded_rectangle, ellipse, polygon or line")
    img = img.resize((W // ss, H // ss), Image.Resampling.BOX)  # exact area coverage, no ringing
    return np.asarray(img).copy()


def render_fill(props: FillProps, width: int, height: int) -> np.ndarray:
    if props.type == "solid":
        c = parse_color(props.color)
        return np.broadcast_to(np.array(c, np.uint8), (height, width, 4)).copy()
    stops = props.stops or [[0.0, "#000000"], [1.0, "#ffffff"]]
    try:
        offs = np.array([float(s[0]) for s in stops], np.float32)
        cols = np.array([parse_color(s[1]) for s in stops], np.float32)
    except (TypeError, IndexError, ValueError) as exc:
        raise ValidationError("Gradient stops must be [[offset, '#rrggbb'], ...]") from exc
    order = np.argsort(offs)
    offs, cols = offs[order], cols[order]
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    if props.type == "linear_gradient":
        rad = np.deg2rad(props.angle)
        dx, dy = np.cos(rad), np.sin(rad)
        proj = (xx - width / 2) * dx + (yy - height / 2) * dy
        half = (abs(width * dx) + abs(height * dy)) / 2
        t = (proj + half) / max(2 * half, 1e-6)
    elif props.type == "radial_gradient":
        cx, cy = props.center[0] * width, props.center[1] * height
        r = props.radius * np.hypot(width, height) / 2
        t = np.hypot(xx - cx, yy - cy) / max(r, 1e-6)
    else:
        raise ValidationError(f"Unknown fill type '{props.type}'")
    t = np.clip(t, 0, 1)
    out = np.stack([np.interp(t, offs, cols[:, i]) for i in range(4)], axis=-1)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


# ----- procedural textures ----------------------------------------------------

def fractal_noise(width: int, height: int, *, scale: float = 0.25, octaves: int = 6, persistence: float = 0.5,
                  seed: int = 0) -> np.ndarray:
    """Value-noise fBm in 0..1 (clouds, fog, terrain variation)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((height, width), np.float32)
    amp, total = 1.0, 0.0
    base = max(2, int(max(width, height) * scale / 64) + 2)
    for o in range(octaves):
        cells = base * (2 ** o)
        gw = max(2, int(cells * width / max(width, height)) + 2)
        gh = max(2, int(cells * height / max(width, height)) + 2)
        grid = rng.random((gh, gw)).astype(np.float32)
        out += amp * cv2.resize(grid, (width, height), interpolation=cv2.INTER_CUBIC)
        total += amp
        amp *= persistence
    out /= total
    lo, hi = np.percentile(out, 1), np.percentile(out, 99)
    return np.clip((out - lo) / max(hi - lo, 1e-6), 0, 1)


def procedural(kind: str, width: int, height: int, params: dict) -> np.ndarray:
    """Return RGBA uint8 procedural content."""
    seed = int(params.get("seed", 0))
    if kind == "clouds":
        n = fractal_noise(width, height, scale=float(params.get("scale", 0.25)),
                          octaves=int(params.get("octaves", 6)), seed=seed)
        c1 = np.array(parse_color(params.get("color_dark", "#000000")), np.float32)
        c2 = np.array(parse_color(params.get("color_light", "#ffffff")), np.float32)
        out = c1 + (c2 - c1) * n[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)
    if kind == "fog":
        n = fractal_noise(width, height, scale=float(params.get("scale", 0.15)), octaves=5, seed=seed)
        density = float(params.get("density", 0.5))
        yy = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        falloff = params.get("vertical_falloff", "bottom")
        g = yy if falloff == "bottom" else (1 - yy if falloff == "top" else np.ones_like(yy))
        alpha = np.clip(n * density * (0.4 + 0.6 * g), 0, 1)
        c = parse_color(params.get("color", "#dfe6ee"))
        out = np.zeros((height, width, 4), np.uint8)
        out[..., :3] = c[:3]
        out[..., 3] = (alpha * 255).astype(np.uint8)
        return out
    if kind == "grain":
        rng = np.random.default_rng(seed)
        g = np.clip(rng.normal(0.5, float(params.get("amount", 0.12)), (height, width)), 0, 1)
        out = np.zeros((height, width, 4), np.uint8)
        out[..., :3] = (g[..., None] * 255).astype(np.uint8)
        out[..., 3] = 255
        return out
    if kind == "bokeh":
        rng = np.random.default_rng(seed)
        out = np.zeros((height, width, 4), np.float32)
        count = int(params.get("count", 40))
        rmin, rmax = float(params.get("min_radius", 8)), float(params.get("max_radius", 40))
        color = np.array(parse_color(params.get("color", "#ffe9b0")), np.float32) / 255
        for _ in range(count):
            cx, cy = rng.uniform(0, width), rng.uniform(0, height)
            r = rng.uniform(rmin, rmax)
            disc = np.zeros((height, width), np.float32)
            cv2.circle(disc, (int(cx), int(cy)), int(r), float(rng.uniform(0.15, 0.6)), -1, cv2.LINE_AA)
            out[..., :3] += disc[..., None] * color[:3]
            out[..., 3] = np.maximum(out[..., 3], disc)
        out = cv2.GaussianBlur(out, (0, 0), float(params.get("softness", 2.0)))
        return np.clip(out * 255, 0, 255).astype(np.uint8)
    if kind == "sky":
        top = params.get("top", "#3d6fb6")
        horizon = params.get("horizon", "#cfe0f2")
        hp = float(params.get("horizon_position", 0.85))
        return render_fill(FillProps(type="linear_gradient", angle=90,
                                     stops=[[0, top], [hp, horizon], [1, horizon]]), width, height)
    if kind == "water":
        n1 = fractal_noise(width, height, scale=float(params.get("scale", 0.4)), octaves=5, seed=seed)
        stretch = cv2.resize(cv2.resize(n1, (width, max(2, height // 4))), (width, height))
        deep = np.array(parse_color(params.get("deep", "#0b3954")), np.float32)
        shallow = np.array(parse_color(params.get("shallow", "#3f88a8")), np.float32)
        yy = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
        base = shallow + (deep - shallow) * yy
        out = base * (0.8 + 0.4 * stretch[..., None])
        out[..., 3] = 255
        return np.clip(out, 0, 255).astype(np.uint8)
    raise ValidationError(f"Unknown procedural kind '{kind}'",
                          hint="Use clouds, fog, grain, bokeh, sky or water")


PROCEDURAL_KINDS = ["clouds", "fog", "grain", "bokeh", "sky", "water"]
