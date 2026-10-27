"""Compatibility shim for the MCP Python SDK.

SDK 2.x renamed ``FastMCP`` to ``mcp.server.mcpserver.MCPServer``; 1.x ships
``mcp.server.fastmcp.FastMCP``. Both expose the same decorator API we use.
"""

from __future__ import annotations

try:  # MCP Python SDK >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.utilities.types import Image as McpImage

    SDK_MAJOR = 2
except ImportError:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]
    from mcp.server.fastmcp import Image as McpImage  # type: ignore[no-redef]

    SDK_MAJOR = 1

try:
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover
    ToolAnnotations = None  # type: ignore[assignment,misc]


def make_server(name: str, instructions: str):
    return _Server(name=name, instructions=instructions)


__all__ = ["McpImage", "SDK_MAJOR", "ToolAnnotations", "make_server"]
