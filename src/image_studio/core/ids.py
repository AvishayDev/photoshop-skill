from __future__ import annotations

import secrets


def new_id(prefix: str) -> str:
    """Stable, collision-resistant identifiers such as ``lyr_3f9a1c2b``."""
    return f"{prefix}_{secrets.token_hex(4)}"
