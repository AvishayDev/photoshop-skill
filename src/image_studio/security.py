"""Filesystem and input-safety helpers.

The MCP server may be driven by an agent that reads untrusted web content, so
every path coming from a tool call is resolved and checked against the
configured allow-lists before it is read or written.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from .config import get_settings
from .errors import PathSecurityError, ValidationError

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP", "TIFF", "BMP", "GIF"}
_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def slugify(name: str, max_len: int = 64) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-.")
    return (slug or "untitled")[:max_len]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_read_path(raw: str | Path) -> Path:
    path = Path(raw).expanduser().resolve()
    roots = get_settings().allowed_read_dirs
    if not any(_is_within(path, r) for r in roots):
        raise PathSecurityError(
            f"Reading '{path}' is outside the allowed directories.",
            hint="Copy the file into the workspace or add its folder to IMAGE_STUDIO_ALLOWED_DIRS.",
            details={"allowed": [str(r) for r in roots]},
        )
    if not path.exists():
        raise ValidationError(f"File does not exist: {path}")
    return path


def resolve_write_path(raw: str | Path, *, base: Path | None = None) -> Path:
    """Resolve an output path. Relative paths are interpreted against ``base`` (usually the project)."""
    p = Path(raw).expanduser()
    if not p.is_absolute() and base is not None:
        p = base / p
    path = p.resolve()
    roots = list(get_settings().allowed_write_dirs)
    if base is not None:
        roots.append(base.resolve())
    if not any(_is_within(path, r) for r in roots):
        raise PathSecurityError(
            f"Writing '{path}' is outside the allowed output directories.",
            hint="Write inside the project folder or add the folder to IMAGE_STUDIO_OUTPUT_DIRS.",
            details={"allowed": [str(r) for r in roots]},
        )
    return path


def safe_child(root: Path, *parts: str) -> Path:
    """Join path parts under ``root`` and refuse traversal outside it."""
    candidate = root.joinpath(*parts).resolve()
    if not _is_within(candidate, root.resolve()):
        raise PathSecurityError(f"Path escapes its root: {'/'.join(parts)}")
    return candidate


def open_image_safely(path: Path) -> Image.Image:
    """Open an untrusted image with a decompression-bomb guard and format allow-list."""
    Image.MAX_IMAGE_PIXELS = get_settings().max_image_pixels
    try:
        img = Image.open(path)
        img.verify()  # detects truncated / malformed files
        img = Image.open(path)
    except Image.DecompressionBombError as exc:
        raise ValidationError(f"Image is too large to open safely: {exc}") from exc
    except Exception as exc:  # PIL raises many types for corrupt input
        raise ValidationError(f"Cannot read image '{path.name}': {exc}") from exc
    if img.format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(f"Unsupported image format {img.format!r}; allowed: {sorted(ALLOWED_IMAGE_FORMATS)}")
    img.load()
    return img
