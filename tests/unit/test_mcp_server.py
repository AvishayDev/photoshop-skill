import asyncio
import json

import pytest

from image_studio.mcp_server.server import create_server
from image_studio.mcp_server.session import Session

ESSENTIAL = {
    "create_project", "open_document", "get_document_info", "save_document", "create_checkpoint",
    "restore_checkpoint", "list_layers", "get_layer_info", "create_layer", "import_image_as_layer",
    "duplicate_layer", "delete_layer", "rename_layer", "move_layer", "set_layer_visibility", "set_layer_opacity",
    "set_blend_mode", "crop_image", "resize_image", "transform_layer", "rotate_layer", "flip_layer",
    "align_layers", "create_selection", "select_by_color", "create_layer_mask", "edit_layer_mask", "invert_mask",
    "feather_mask", "apply_mask", "clone_stamp", "heal_region", "remove_object", "remove_background",
    "apply_filter", "adjust_colors", "adjust_curves", "blur_layer", "sharpen_layer", "create_text_layer",
    "create_shape_layer", "add_drop_shadow", "add_lighting_effect", "create_reflection", "blend_layers",
    "search_references", "get_reference_metadata", "analyze_visual_references", "render_preview", "inspect_image",
    "compare_images", "export_png", "export_jpeg", "export_webp", "get_project_manifest", "submit_plan",
    "search_knowledge", "save_knowledge", "get_capabilities",
}


def run(coro):
    return asyncio.run(coro)


def _content(res):
    """In-process call_tool returns a CallToolResult (SDK 2) or (content, structured) / content (SDK 1)."""
    if isinstance(res, tuple):
        content, structured = res
        if isinstance(content, list) and content and hasattr(content[0], "content"):
            content = content[0].content
        return content, structured, None
    if isinstance(res, list):
        return res, None, None
    data = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    return res.content, data, bool(getattr(res, "is_error", getattr(res, "isError", False)))


def call(server, name, args):
    content, data, is_error = _content(run(server.call_tool(name, args)))
    if data is None:
        data = json.loads(content[0].text)
    if isinstance(data, dict) and "result" in data and len(data) == 1:
        data = data["result"]
    if is_error is None:
        is_error = isinstance(data, dict) and data.get("ok") is False
    return data, is_error


@pytest.fixture
def server(settings):
    return create_server(Session())


def test_tool_inventory_and_schemas(server):
    tools = run(server.list_tools())
    names = {t.name for t in tools}
    assert ESSENTIAL <= names
    for t in tools:
        assert t.description and len(t.description) > 20, t.name
        schema = getattr(t, "input_schema", None) or t.inputSchema
        assert schema["type"] == "object"
    clone = next(t for t in tools if t.name == "clone_stamp")
    props = (getattr(clone, "input_schema", None) or clone.inputSchema)["properties"]
    assert "description" in props["strokes"] and props["source_point"]["minItems"] == 2


def test_plan_gate_and_workflow(server, photo):
    data, err = call(server, "create_project", {"name": "Gate", "width": 64, "height": 64})
    assert err and data["error"]["code"] == "plan_required"
    data, err = call(server, "submit_plan", {"request": "crop", "steps": ["Crop it now please"] * 3})
    assert err and data["error"]["code"] == "invalid_parameter"
    draft, _ = call(server, "draft_plan", {"request": "Crop this photo to a square"})
    data, err = call(server, "submit_plan", {"request": "Crop this photo to a square", "steps": draft["steps"]})
    assert not err and data["step_count"] >= 10
    opened, err = call(server, "open_document", {"path": str(photo)})
    assert not err
    d = opened["document_id"]
    layers, _ = call(server, "list_layers", {"document_id": d})
    orig = layers["layers"][0]["id"]
    dup, _ = call(server, "duplicate_layer", {"document_id": d, "layer_id": orig})
    call(server, "create_checkpoint", {"document_id": d, "name": "before crop"})
    cropped, err = call(server, "crop_image", {"document_id": d, "x": 40, "y": 0, "width": 120, "height": 120})
    assert not err and cropped["document"]["width"] == 120
    prev, err = call(server, "render_preview", {"document_id": d, "max_size": 128})
    assert not err
    insp, err = call(server, "inspect_image", {"document_id": d})
    assert not err and "stats" in insp
    exp, err = call(server, "export_png", {"document_id": d})
    assert not err and exp["verification"]["matches"] and exp["size"] == [120, 120]
    man, _ = call(server, "get_project_manifest", {"document_id": d})
    assert man["plans"] and exp["export_path"] in man["exports"]
    done, err = call(server, "complete_plan", {"summary": "Cropped to square"})
    assert not err
    data, err = call(server, "rename_layer", {"document_id": d, "layer_id": dup["layer_id"], "name": "x"})
    assert err and data["error"]["code"] == "plan_required"


def test_errors_are_structured(server):
    data, err = call(server, "get_document_info", {"document_id": "doc_nope"})
    assert err and data["error"]["code"] == "not_found" and data["error"]["hint"]


def test_view_image_returns_image_content(server, photo):
    content, _, _ = _content(run(server.call_tool("view_image", {"path": str(photo), "max_size": 64})))
    kinds = [c.type for c in content]
    assert "image" in kinds


def test_capabilities_tool(server):
    data, err = call(server, "get_capabilities", {})
    assert not err and data["backends"]["pillow"]["available"] and data["plan_gate"]["require_plan"]
