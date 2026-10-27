"""End-to-end: launch `image-studio serve` as a subprocess and drive it with the official MCP client,
exactly like Claude Code / Codex do over stdio."""

import json
import os
import sys

import anyio
import pytest


def _result_json(res):
    data = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    return data if data is not None else json.loads(res.content[0].text)


async def _session(workspace, fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = {**os.environ, "IMAGE_STUDIO_WORKSPACE": str(workspace), "PYTHONUNBUFFERED": "1"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "image_studio.cli", "serve"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def test_stdio_end_to_end(tmp_path):
    async def flow(s):
        tools = await s.list_tools()
        names = {t.name for t in tools.tools}
        assert {"submit_plan", "create_project", "export_png"} <= names
        draft = _result_json(await s.call_tool("draft_plan", {"request": "Create a sunset poster with a title"}))
        plan = _result_json(await s.call_tool("submit_plan", {"request": "Create a sunset poster with a title",
                                                              "steps": draft["steps"]}))
        assert plan["ok"]
        proj = _result_json(await s.call_tool("create_project", {"name": "Poster", "width": 320, "height": 200}))
        d = proj["document_id"]
        await s.call_tool("create_fill_layer", {"document_id": d, "type": "linear_gradient",
                                                "stops": [[0, "#ff9a3c"], [1, "#3c1053"]]})
        await s.call_tool("create_text_layer", {"document_id": d, "text": "SUNSET", "x": 20, "y": 20, "size": 40})
        prev = _result_json(await s.call_tool("render_preview", {"document_id": d}))
        view = await s.call_tool("view_image", {"path": prev["preview_path"], "max_size": 128})
        assert any(c.type == "image" for c in view.content)
        exp = _result_json(await s.call_tool("export_png", {"document_id": d}))
        return exp

    try:
        exp = anyio.run(_session, tmp_path / "ws", flow)
    except ModuleNotFoundError as exc:  # pragma: no cover
        pytest.skip(f"MCP client unavailable: {exc}")
    assert exp["verification"]["matches"] and exp["size"] == [320, 200]
