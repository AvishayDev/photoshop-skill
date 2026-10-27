"""The :class:`Editor` facade combining all operation groups."""

from __future__ import annotations

from .content import ContentOps
from .documents import DocumentOps
from .layers import LayerOps
from .masking import MaskOps
from .output import OutputOps
from .retouching import RetouchOps
from .transform import TransformOps


class Editor(ContentOps, RetouchOps, MaskOps, TransformOps, LayerOps, OutputOps, DocumentOps):
    """Single entry point for every editing operation.

    Every mutating method runs inside a project transaction: the document is
    committed atomically with a new revision and a history entry, or not at all.
    """
