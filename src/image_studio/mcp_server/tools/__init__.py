"""MCP tool groups."""

from . import content, documents, inspection, layers, masks, output, painting, planning, research, retouch


def register_all(reg, session) -> None:
    for mod in (planning, documents, layers, masks, retouch, content, painting, output, inspection, research):
        mod.register(reg, session)
