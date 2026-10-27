from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from image_studio.config import Settings, set_settings

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    s = Settings(workspace=ws, knowledge_dir=tmp_path / "knowledge", cache_dir=tmp_path / "cache",
                 allowed_read_dirs=[tmp_path, REPO / "tests" / "fixtures"], allowed_write_dirs=[ws],
                 require_plan=True, gimp_executable=os.environ.get("IMAGE_STUDIO_GIMP"))
    set_settings(s)
    yield s
    set_settings(None)


@pytest.fixture
def editor(settings):
    from image_studio.editor import Editor
    return Editor()


@pytest.fixture
def doc(editor):
    return editor.create_project("Test", 200, 120, background="#808080")["document_id"]


@pytest.fixture
def photo(tmp_path) -> Path:
    """Deterministic synthetic 'photo': gradient sky, textured ground, red disc subject."""
    h, w = 120, 200
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.zeros((h, w, 3), np.uint8)
    img[..., 0] = 90 + yy // 3
    img[..., 1] = 140 + yy // 4
    img[..., 2] = 210 - yy // 3
    rng = np.random.default_rng(1)
    ground = yy > 80
    img[ground] = (np.array([90, 120, 60]) + rng.integers(-20, 20, (ground.sum(), 3))).clip(0, 255)
    disc = (xx - 100) ** 2 + (yy - 60) ** 2 < 20 ** 2
    img[disc] = [200, 30, 30]
    p = tmp_path / "photo.png"
    Image.fromarray(img).save(p)
    return p


def gimp_available() -> bool:
    from image_studio.backends.gimp import GimpBackend
    return GimpBackend().status().available
