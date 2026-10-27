"""Regenerate docs/editing-tools.md from the live MCP tool definitions (single source of truth)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from image_studio.mcp_server.server import create_server

GROUPS = [
    ("Planning & capabilities", ["get_capabilities", "draft_plan", "submit_plan", "get_plan", "complete_plan"]),
    ("Projects & documents", ["create_project", "open_document", "list_projects", "get_document_info",
                              "get_project_manifest", "get_history", "save_document", "create_checkpoint",
                              "list_checkpoints", "restore_checkpoint", "undo", "crop_image", "resize_image",
                              "resize_canvas"]),
    ("Layers & transforms", None),
    ("Selections & masks", ["create_selection", "select_by_color", "select_layer_alpha", "modify_selection",
                            "create_layer_mask", "edit_layer_mask", "invert_mask", "feather_mask",
                            "set_mask_enabled", "apply_mask", "delete_mask"]),
    ("Retouching, filters & color", ["apply_filter", "describe_gimp_filter", "adjust_colors", "adjust_curves",
                                     "update_adjustment_layer", "match_color", "blur_layer", "sharpen_layer",
                                     "clone_stamp", "heal_region", "remove_object", "remove_background"]),
    ("Content & compositing", ["create_text_layer", "update_text_layer", "create_shape_layer", "create_fill_layer",
                               "create_procedural_layer", "add_layer_effect", "add_drop_shadow",
                               "remove_layer_effect", "add_cast_shadow", "add_contact_shadow", "create_reflection",
                               "add_lighting_effect", "generate_image_layer"]),
    ("Preview, inspection & output", ["render_preview", "view_image", "inspect_image", "compare_images",
                                      "analyze_layer_integration", "export_image", "export_png", "export_jpeg",
                                      "export_webp"]),
    ("Research & knowledge", ["search_knowledge", "read_knowledge", "save_knowledge", "search_references",
                              "get_reference_metadata", "fetch_reference", "analyze_visual_references",
                              "record_observation", "get_research_summary"]),
]


def _type(schema: dict) -> str:
    if "anyOf" in schema:
        return " or ".join(_type(s) for s in schema["anyOf"])
    t = schema.get("type", "any")
    if t == "array":
        return f"array<{_type(schema.get('items', {}))}>"
    return t


def main() -> None:
    server = create_server()
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    used = {n for _, names in GROUPS if names for n in names}
    lines = ["# Tool reference", "",
             "Generated from the MCP server by `python scripts/gen_tool_docs.py` - do not edit by hand.", "",
             "All tools return JSON with `ok`. Errors return `{ok: false, error: {code, message, hint}}` and are "
             "flagged as MCP errors. Tools marked **mutating** require an active plan (`submit_plan`).", ""]
    for title, names in GROUPS:
        names = names or sorted(n for n in tools if n not in used)
        lines += [f"## {title}", ""]
        for n in names:
            t = tools[n]
            schema = getattr(t, "input_schema", None) or t.inputSchema
            gated = n in server._image_studio_mutating
            lines.append(f"### `{n}`" + (" (mutating)" if gated else ""))
            lines.append("")
            lines.append((t.description or "").strip())
            lines.append("")
            props = schema.get("properties", {})
            req = set(schema.get("required", []))
            if props:
                lines.append("| parameter | type | default |")
                lines.append("| --- | --- | --- |")
                for pname, ps in props.items():
                    default = "required" if pname in req else json.dumps(ps.get("default"))
                    lines.append(f"| `{pname}` | {_type(ps)} | {default} |")
                lines.append("")
    Path("docs/editing-tools.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote docs/editing-tools.md ({len(tools)} tools)")


if __name__ == "__main__":
    main()
