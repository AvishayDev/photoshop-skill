from __future__ import annotations

from typing import Any

from .common import DocId


def register(tool, session) -> None:
    ed = session.editor

    @tool(mutating=True, title="Create project")
    def create_project(name: str, width: int, height: int, background: str | None = "#ffffff",
                       resolution_dpi: float = 72.0) -> dict[str, Any]:
        """Create a new editable project (document) in the workspace. background: '#rrggbb' fill layer,
        or 'transparent'/null for none. Returns document_id and the project folder."""
        return ed.create_project(name, width, height, background, resolution_dpi)

    @tool(mutating=True, title="Open document")
    def open_document(path: str, name: str | None = None) -> dict[str, Any]:
        """Open an image (PNG/JPEG/WebP/TIFF/BMP/GIF) as a new project with a LOCKED 'Original' layer,
        a layered file (.ora always; .xcf/.psd via GIMP 3), or an existing project folder to continue editing."""
        return ed.open_document(path, name)

    @tool(read_only=True, title="List projects")
    def list_projects() -> dict[str, Any]:
        """List projects in the workspace with their document ids."""
        return ed.list_projects()

    @tool(read_only=True, title="Document info")
    def get_document_info(document_id: DocId) -> dict[str, Any]:
        """Canvas size, color mode, revision, layer tree (top to bottom), checkpoints, assets and metadata."""
        return ed.get_document_info(document_id)

    @tool(read_only=True, title="Project manifest")
    def get_project_manifest(document_id: DocId) -> dict[str, Any]:
        """Paths of the project, exports, previews, research records, plans and assets with licenses."""
        return ed.get_project_manifest(document_id)

    @tool(read_only=True, title="History")
    def get_history(document_id: DocId, limit: int = 30) -> dict[str, Any]:
        """Recent operations with parameters, affected layers, backend and warnings."""
        return ed.get_history(document_id, limit)

    @tool(title="Save document")
    def save_document(document_id: DocId, format: str = "project", path: str | None = None) -> dict[str, Any]:
        """Save the project. format: project (always saved anyway) | ora (OpenRaster, always available) |
        xcf (native GIMP file, needs GIMP 3) | psd (needs local Photoshop). path is relative to the project
        folder unless absolute inside an allowed output directory."""
        return ed.save_document(document_id, format, path)

    @tool(title="Create checkpoint")
    def create_checkpoint(document_id: DocId, name: str, note: str | None = None) -> dict[str, Any]:
        """Pin the current state under a name so it can be restored later (cheap: no pixels are copied)."""
        return ed.create_checkpoint(document_id, name, note)

    @tool(read_only=True, title="List checkpoints")
    def list_checkpoints(document_id: DocId) -> dict[str, Any]:
        """List named checkpoints."""
        return ed.list_checkpoints(document_id)

    @tool(mutating=True, title="Restore checkpoint")
    def restore_checkpoint(document_id: DocId, checkpoint: str) -> dict[str, Any]:
        """Restore a checkpoint (by id or name). Recorded as a new revision, so it can itself be undone."""
        return ed.restore_checkpoint(document_id, checkpoint)

    @tool(mutating=True, title="Undo")
    def undo(document_id: DocId, steps: int = 1) -> dict[str, Any]:
        """Return to the state from `steps` operations ago (recorded as a new revision)."""
        return ed.undo(document_id, steps)

    @tool(mutating=True, title="Crop image")
    def crop_image(document_id: DocId, x: int, y: int, width: int, height: int) -> dict[str, Any]:
        """Crop the canvas to a rectangle. Non-destructive: layer pixels outside the canvas are kept."""
        return ed.crop_image(document_id, x, y, width, height)

    @tool(mutating=True, title="Resize image")
    def resize_image(document_id: DocId, width: int | None = None, height: int | None = None,
                     scale: float | None = None, interpolation: str = "lanczos") -> dict[str, Any]:
        """Scale the whole document (all layers and masks). Give width and/or height (aspect kept if one is
        omitted) or scale. interpolation: nearest | linear | cubic | lanczos | area."""
        return ed.resize_image(document_id, width, height, scale, interpolation)

    @tool(mutating=True, title="Resize canvas")
    def resize_canvas(document_id: DocId, width: int, height: int, anchor: str = "center") -> dict[str, Any]:
        """Change canvas size without scaling content. anchor: center, top_left, top, top_right, left, right,
        bottom_left, bottom, bottom_right."""
        return ed.resize_canvas(document_id, width, height, anchor)
