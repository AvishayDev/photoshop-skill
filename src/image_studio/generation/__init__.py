"""Optional image-generation providers.

No provider is required. The built-in procedural textures live in
``image_studio.core.render``; this package adds ML generators that run
locally (ComfyUI). Paid cloud APIs are intentionally not part of the core.
"""

from __future__ import annotations

from ..errors import ProviderUnavailableError
from .base import ImageGenerator
from .comfyui import ComfyUIGenerator


def available_generators() -> dict[str, ImageGenerator]:
    return {"comfyui": ComfyUIGenerator()}


def get_generator(name: str) -> ImageGenerator:
    gens = available_generators()
    if name not in gens:
        raise ProviderUnavailableError(f"Unknown generator '{name}'", details={"available": list(gens)})
    gen = gens[name]
    st = gen.status()
    if not st["available"]:
        raise ProviderUnavailableError(f"Generator '{name}' is not available: {st['detail']}",
                                       hint=st.get("how_to_enable"))
    return gen


__all__ = ["ImageGenerator", "available_generators", "get_generator"]
