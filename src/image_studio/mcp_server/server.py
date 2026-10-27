"""MCP server entry point.

Run with ``image-studio serve`` (stdio transport, which Claude Code and Codex
use for local servers). Every tool returns a JSON object with ``ok``; failures
return ``{"ok": false, "error": {"code", "message", "hint"}}`` instead of
crashing, so the agent can recover.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import traceback
from collections.abc import Callable
from typing import Any

from ..errors import StudioError
from .compat import ToolAnnotations, make_server
from .session import Session

log = logging.getLogger("image_studio.mcp")

INSTRUCTIONS = """\
Agent Image Studio: create images from scratch by painting (no generative AI) and edit images with
Photoshop-like layer tools.

Mandatory workflow for EVERY image creation or editing request:
1. Call get_capabilities once per session to learn what this installation can do.
2. Show the user a numbered plan of >= 10 meaningful steps adapted to the request
   (draft_plan can suggest one), then register it with submit_plan. Mutating tools
   refuse to run without an active plan.
3. search_patterns and search_knowledge BEFORE researching: reuse what was learned before.
4. Research what is missing (search_references, fetch_reference, LOOK at the images), measure it
   with learn_pattern (palette, stripes/spots, silhouette) and save_pattern the useful results.
5. Create: paint layers (list_paint_actions, paint_layer, run_pipeline - or write a Python pipeline with
   image_studio.pipeline.Pipeline) - environment, subject figure, light, shadows, reflections, grade.
   Edit: non-destructive layers, masks, adjustment layers and checkpoints.
6. After each significant stage: render_preview, LOOK at the image (view_image or open the
   file), run inspect_image / analyze_layer_integration, and correct defects.
7. Deliver: save_document (native .xcf/.ora when possible), export, verify, report paths,
   limitations and attribution; complete_plan; save_knowledge / save_pattern for reusable lessons.
Coordinates are document pixels, origin top-left, y down. Layer ids are stable.
"""


def _wrap(session: Session, fn: Callable[..., Any], *, mutating: bool) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            if mutating:
                session.check_plan(fn.__name__)
            result = fn(*args, **kwargs)
            if mutating and isinstance(result, dict) and result.get("document_id"):
                session.attach_plan(result["document_id"])
            return result
        except StudioError as exc:
            return _error_result(exc.to_dict())
        except Exception as exc:  # never crash the server on a tool error
            log.error("tool %s failed: %s\n%s", fn.__name__, exc, traceback.format_exc())
            return _error_result({"ok": False, "error": {
                "code": "internal_error", "message": f"{type(exc).__name__}: {exc}",
                "hint": "This is likely a bug; the project was not modified (operations are atomic)."}})
    sig = inspect.signature(fn, eval_str=True)
    wrapper.__signature__ = sig  # type: ignore[attr-defined]
    wrapper.__annotations__ = {**{n: p.annotation for n, p in sig.parameters.items()},
                               "return": sig.return_annotation}
    return wrapper


def _error_result(payload: dict[str, Any]):
    """Structured error payload flagged with isError so clients render it as a failed call."""
    try:
        from mcp.types import CallToolResult
        return CallToolResult.model_validate({"content": [{"type": "text", "text": json.dumps(payload, indent=1)}],
                                              "structuredContent": payload, "isError": True})
    except Exception:  # older SDKs: plain structured error
        return payload


class ToolRegistrar:
    """Registers plain functions as MCP tools with plan gating, error handling and annotations."""

    def __init__(self, mcp, session: Session):
        self.mcp = mcp
        self.session = session
        self.names: list[str] = []
        self.mutating: set[str] = set()

    def __call__(self, *, mutating: bool = False, read_only: bool = False, destructive: bool = False,
                 open_world: bool = False, title: str | None = None):
        def deco(fn):
            ann = None
            if ToolAnnotations is not None:
                ann = ToolAnnotations(title=title, readOnlyHint=read_only, destructiveHint=destructive,
                                      openWorldHint=open_world)
            wrapped = _wrap(self.session, fn, mutating=mutating)
            self.mcp.add_tool(wrapped, name=fn.__name__, description=inspect.getdoc(fn), annotations=ann)
            self.names.append(fn.__name__)
            if mutating:
                self.mutating.add(fn.__name__)
            return fn
        return deco


def create_server(session: Session | None = None):
    from .tools import register_all

    session = session or Session()
    mcp = make_server("agent-image-studio", INSTRUCTIONS)
    reg = ToolRegistrar(mcp, session)
    register_all(reg, session)
    mcp._image_studio_session = session  # for tests and diagnostics
    mcp._image_studio_tools = reg.names
    mcp._image_studio_mutating = reg.mutating
    return mcp


def main(transport: str = "stdio") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = create_server()
    server.run(transport=transport)


if __name__ == "__main__":
    main()
