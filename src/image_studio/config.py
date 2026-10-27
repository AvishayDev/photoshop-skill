"""Runtime configuration, resolved from environment variables.

All settings have safe defaults so the toolkit works immediately after
installation. See docs/installation.md for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_paths(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def find_repo_root(start: Path | None = None) -> Path | None:
    """Return the nearest directory containing this project's ``knowledge/`` and ``pyproject.toml``."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "knowledge").is_dir():
            return parent
    return None


@dataclass
class Settings:
    workspace: Path
    knowledge_dir: Path
    cache_dir: Path
    allowed_read_dirs: list[Path] = field(default_factory=list)
    allowed_write_dirs: list[Path] = field(default_factory=list)
    require_plan: bool = True
    backend: str = "auto"  # auto | pillow | gimp | photoshop
    gimp_executable: str | None = None
    gimp_timeout: float = 180.0
    max_image_pixels: int = 120_000_000
    max_revisions: int = 100
    user_agent: str = (
        "agent-image-studio/0.1 (https://github.com/avishaydev/photoshop-skill; open-source image toolkit)"
    )
    comfyui_url: str | None = None
    comfyui_checkpoint: str | None = None
    openverse_token: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        repo = find_repo_root(Path.cwd()) or find_repo_root()
        base = repo or Path.cwd()
        workspace = Path(os.environ.get("IMAGE_STUDIO_WORKSPACE", base / "projects")).expanduser().resolve()
        knowledge = Path(os.environ.get("IMAGE_STUDIO_KNOWLEDGE_DIR", base / "knowledge")).expanduser().resolve()
        cache = Path(os.environ.get("IMAGE_STUDIO_CACHE_DIR", base / ".image_studio_cache")).expanduser().resolve()
        reads = [workspace, Path.cwd().resolve(), *_env_paths("IMAGE_STUDIO_ALLOWED_DIRS")]
        if repo:
            reads.append(repo / "examples")
        writes = [workspace, *_env_paths("IMAGE_STUDIO_OUTPUT_DIRS")]
        return cls(
            workspace=workspace,
            knowledge_dir=knowledge,
            cache_dir=cache,
            allowed_read_dirs=reads,
            allowed_write_dirs=writes,
            require_plan=_env_bool("IMAGE_STUDIO_REQUIRE_PLAN", True),
            backend=os.environ.get("IMAGE_STUDIO_BACKEND", "auto").lower(),
            gimp_executable=os.environ.get("IMAGE_STUDIO_GIMP") or None,
            gimp_timeout=float(os.environ.get("IMAGE_STUDIO_GIMP_TIMEOUT", "180")),
            max_image_pixels=int(os.environ.get("IMAGE_STUDIO_MAX_PIXELS", "120000000")),
            max_revisions=int(os.environ.get("IMAGE_STUDIO_MAX_REVISIONS", "100")),
            comfyui_url=os.environ.get("IMAGE_STUDIO_COMFYUI_URL") or None,
            comfyui_checkpoint=os.environ.get("IMAGE_STUDIO_COMFYUI_CHECKPOINT") or None,
            openverse_token=os.environ.get("IMAGE_STUDIO_OPENVERSE_TOKEN") or None,
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """Override settings (used by tests and embedding applications)."""
    global _settings
    _settings = settings
