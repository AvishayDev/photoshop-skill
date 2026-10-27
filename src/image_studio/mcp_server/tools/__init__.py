"""MCP tool groups."""

from . import content, documents, inspection, layers, masks, output, planning, research, retouch


def register_all(reg, session) -> None:
    for mod in (planning, documents, layers, masks, retouch, content, output, inspection, research):
        mod.register(reg, session)
