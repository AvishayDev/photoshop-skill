import io

import numpy as np
import pytest
from PIL import Image

from image_studio.errors import ProviderUnavailableError
from image_studio.generation.comfyui import ComfyUIGenerator


class Resp:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content, self.text = status, data, content, str(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeComfy:
    """Minimal fake of the ComfyUI HTTP API (object_info, prompt, history, view)."""

    def __init__(self):
        self.posted = None

    def get(self, url, params=None, timeout=None):
        if url.endswith("/object_info/CheckpointLoaderSimple"):
            return Resp(data={"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["model.safetensors"]]}}}})
        if "/history/" in url:
            return Resp(data={"p1": {"status": {"status_str": "success"}, "outputs": {
                "9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}})
        if url.endswith("/view"):
            buf = io.BytesIO()
            Image.fromarray(np.full((64, 96, 3), 200, np.uint8)).save(buf, "PNG")
            return Resp(content=buf.getvalue())
        return Resp(404)

    def post(self, url, json=None, timeout=None):
        self.posted = json
        return Resp(data={"prompt_id": "p1"})


def test_unconfigured_is_unavailable(settings):
    st = ComfyUIGenerator().status()
    assert not st["available"] and "COMFYUI_URL" in st["detail"]


def test_remote_urls_refused(settings):
    st = ComfyUIGenerator(url="https://comfy.example.com").status()
    assert not st["available"] and "local" in st["detail"]


def test_generate_with_fake_server(settings):
    fake = FakeComfy()
    gen = ComfyUIGenerator(url="http://127.0.0.1:8188", session=fake)
    rgba, meta = gen.generate(prompt="a red fox", width=100, height=70, seed=42, steps=10)
    wf = fake.posted["prompt"]
    assert wf["6"]["inputs"]["text"] == "a red fox" and wf["3"]["inputs"]["seed"] == 42
    assert wf["5"]["inputs"]["width"] == 96 and wf["5"]["inputs"]["height"] == 64  # multiples of 8
    assert rgba.shape == (64, 96, 4) and meta["model"] == "model.safetensors"


def test_editor_reports_missing_provider(editor, doc):
    with pytest.raises(ProviderUnavailableError):
        editor.generate_image_layer(doc, "a fox")
