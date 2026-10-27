from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

DocId = Annotated[str, Field(description="Document id returned by create_project/open_document, e.g. 'doc_1a2b3c4d'")]
LayerId = Annotated[str, Field(description="Stable layer id from list_layers, e.g. 'lyr_9f8e7d6c'")]
OptLayerId = Annotated[str | None, Field(description="Optional stable layer id")]
Point = Annotated[list[float], Field(description="[x, y] in document pixels (origin top-left, y down)",
                                     min_length=2, max_length=2)]
Points = Annotated[list[list[float]], Field(description="List of [x, y] document-pixel points")]
Strokes = Annotated[list[list[list[float]]], Field(
    description="Brush strokes: a list of strokes, each a list of [x, y] document-pixel points, e.g. "
                "[[[120, 80], [160, 82], [200, 90]]]")]
Rect = Annotated[list[float], Field(description="[x, y, width, height] in document pixels", min_length=4,
                                    max_length=4)]
Params = Annotated[dict[str, Any] | None, Field(description="Operation parameters (see the tool description)")]
Color = Annotated[str, Field(description="Color as '#rrggbb' or '#rrggbbaa'")]
