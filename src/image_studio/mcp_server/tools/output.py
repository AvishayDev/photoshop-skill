from __future__ import annotations

import io
from typing import Any

from PIL import Image

from ...errors import ValidationError
from ...security import resolve_read_path
from ..compat import McpImage
from .common import DocId, Rect


def register(tool, session) -> None:
    ed = session.editor

    @tool(read_only=True, title="Render preview")
    def render_preview(document_id: DocId, max_size: int = 1024, layer_id: str | None = None,
                       region: Rect | None = None, background: str = "checkerboard",
                       hide_layers: list[str] | None = None) -> dict[str, Any]:
        """Render the current composite (or one layer solo, or a region at full resolution for 100% crops)
        to previews/. Then LOOK at it with view_image (or by opening the file) and inspect for defects."""
        return ed.render_preview(document_id, max_size, layer_id, [int(v) for v in region] if region else None,
                                 background, hide_layers)

    def view_image(path: str, max_size: int = 1024):
        """Return an image file (preview, export, reference, contact sheet) as image content so you can see
        it. Downscaled to max_size. Use after every render_preview."""
        p = resolve_read_path(path)
        if not 64 <= max_size <= 2048:
            raise ValidationError("max_size must be within 64..2048")
        with Image.open(p) as im:
            im = im.convert("RGBA")
            im.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            im.save(buf, "PNG")
        return McpImage(data=buf.getvalue(), format="png")
    tool(read_only=True, title="View image")(view_image)

    @tool(title="Export image")
    def export_image(document_id: DocId, path: str | None = None, format: str = "png", quality: int = 92,
                     width: int | None = None, height: int | None = None,
                     background: str | None = None) -> dict[str, Any]:
        """Export a flattened copy (the project stays layered): png | jpeg | webp | tiff. Optional resize.
        JPEG gets a white background unless `background` is given. Verifies the written file (opens it,
        checks format and size) and writes a .credits.json sidecar with sources and licenses."""
        return ed.export_image(document_id, path, format, quality, width, height, background)

    @tool(title="Export PNG")
    def export_png(document_id: DocId, path: str | None = None, width: int | None = None,
                   height: int | None = None) -> dict[str, Any]:
        """Export PNG (keeps transparency) with verification and credits sidecar."""
        return ed.export_image(document_id, path, "png", width=width, height=height)

    @tool(title="Export JPEG")
    def export_jpeg(document_id: DocId, path: str | None = None, quality: int = 92, width: int | None = None,
                    height: int | None = None) -> dict[str, Any]:
        """Export JPEG (quality 1..100) with verification and credits sidecar."""
        return ed.export_image(document_id, path, "jpeg", quality, width, height)

    @tool(title="Export WebP")
    def export_webp(document_id: DocId, path: str | None = None, quality: int = 90, width: int | None = None,
                    height: int | None = None) -> dict[str, Any]:
        """Export WebP with verification and credits sidecar."""
        return ed.export_image(document_id, path, "webp", quality, width, height)
