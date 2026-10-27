"""Capability model: which operations exist, which engine performs them, and what is missing.

The agent calls ``get_capabilities`` before planning so it never relies on an
operation the active installation cannot perform.
"""

from __future__ import annotations

import functools
from typing import Any

from ..backends.base import Backend


@functools.lru_cache(maxsize=1)
def backends() -> dict[str, Backend]:
    from ..backends.gimp import GimpBackend
    from ..backends.photoshop import PhotoshopBackend
    from ..backends.pillow import PillowBackend

    return {"pillow": PillowBackend(), "gimp": GimpBackend(), "photoshop": PhotoshopBackend()}


# operation -> (engine description, backends offering a native/alternative implementation)
OPERATIONS: dict[str, dict[str, Any]] = {
    "documents_layers_groups_history": {"engine": "core", "native": []},
    "masks_selections_clipping": {"engine": "core", "native": []},
    "blend_modes_compositing": {"engine": "core", "native": [],
                                "note": "W3C compositing formulas; GIMP/Photoshop render some modes slightly differently"},
    "transforms_perspective": {"engine": "core (OpenCV)", "native": []},
    "adjustments_and_adjustment_layers": {"engine": "core", "native": []},
    "filters": {"engine": "pillow", "native": ["gimp"],
                "note": "Core filter names (gaussian_blur, ...) or GEGL operations ('gegl:...') with backend='gimp'"},
    "clone_stamp": {"engine": "pillow", "native": ["gimp"]},
    "heal": {"engine": "pillow (Poisson clone / inpaint)", "native": ["gimp"]},
    "remove_object": {"engine": "pillow (OpenCV inpainting)", "native": [],
                      "note": "Good for small/medium distractions on textured backgrounds; large areas need clone/heal or synthesize_texture"},
    "remove_background": {"engine": "pillow (GrabCut / color key)", "native": [],
                          "note": "Optional 'rembg' method if the rembg package is installed"},
    "text_shapes_fills_procedural": {"engine": "core (Pillow)", "native": []},
    "shadows_reflections_lighting": {"engine": "core", "native": []},
    "native_project_ora": {"engine": "pillow", "native": []},
    "native_project_xcf": {"engine": "gimp", "native": ["gimp"]},
    "native_project_psd_export": {"engine": "photoshop", "native": ["photoshop"]},
    "open_psd": {"engine": "gimp", "native": ["gimp"]},
    "export_png_jpeg_webp_tiff": {"engine": "core", "native": []},
    "procedural_painting": {"engine": "core (image_studio.paint)", "native": [],
                            "note": "Creates images from scratch: sky, clouds, ocean, forest, grass, figures "
                                    "(subjects from pattern-library recipes), patterns, light, shadows, "
                                    "reflections. No generative model is used."},
    "pattern_learning_library": {"engine": "core (image_studio.patterns)", "native": [],
                                 "note": "learn_pattern measures palettes, stripes/spots, silhouettes on "
                                         "references; search/save_pattern persist them in knowledge/patterns"},
    "texture_synthesis": {"engine": "core (patch quilting)", "native": []},
    "reference_research": {"engine": "providers: wikimedia_commons, openverse, local", "native": []},
}


def capability_report(check_gimp_filters: bool = False) -> dict[str, Any]:
    bs = backends()
    statuses = {name: b.status().to_dict() for name, b in bs.items()}
    ops = {}
    for op, info in OPERATIONS.items():
        engine = info["engine"]
        primary = engine.split(" ")[0]
        available = True
        if primary in bs:
            available = statuses[primary]["available"]
        native = [n for n in info["native"] if statuses.get(n, {}).get("available")]
        ops[op] = {**info, "available": available or bool(native), "native_available": native}
    out: dict[str, Any] = {"backends": statuses, "operations": ops}
    try:
        import rembg  # noqa: F401
        out["optional"] = {"rembg": True}
    except Exception:
        out["optional"] = {"rembg": False}
    if check_gimp_filters and statuses["gimp"]["available"]:
        out["gimp_gegl_operations"] = bs["gimp"].filters()
    out["limitations"] = [
        "Color: 8-bit sRGB RGB(A) documents only; CMYK and 16/32-bit are converted to 8-bit sRGB on import.",
        "New subjects are PAINTED procedurally (figure recipes + learned patterns + lighting): results are "
        "painterly/illustrative realism, not photographs. Close-up photorealistic faces/anatomy are beyond "
        "the engine; say so and offer a wider framing or compositing a licensed photo instead.",
        "OpenRaster export bakes masks into alpha; XCF export (GIMP) keeps masks; adjustment layers and "
        "effects are baked into separate raster layers in native exports.",
    ]
    return out
