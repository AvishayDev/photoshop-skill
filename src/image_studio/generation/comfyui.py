"""Local ComfyUI provider (https://github.com/comfyanonymous/ComfyUI).

Talks to a ComfyUI server the user runs locally, through its HTTP API:
``POST /prompt`` (queue an API-format workflow), ``GET /history/<id>``
(poll), ``GET /view`` (download output) and ``GET /object_info`` (discover
installed checkpoints). Configure with:

    IMAGE_STUDIO_COMFYUI_URL=http://127.0.0.1:8188
    IMAGE_STUDIO_COMFYUI_CHECKPOINT=<checkpoint file name>   # optional

Model weights, their licenses and GPU requirements are the user's choice;
see docs/generation.md. Only loopback / private addresses are accepted by
default so prompts are never sent to a remote service by accident.
"""

from __future__ import annotations

import io
import ipaddress
import random
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image

from ..config import get_settings
from ..errors import ProviderUnavailableError, ValidationError
from .base import ImageGenerator

DEFAULT_WORKFLOW: dict[str, Any] = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 25, "cfg": 6.5, "sampler_name": "dpmpp_2m",
                                               "scheduler": "karras", "denoise": 1.0, "model": ["4", 0],
                                               "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "agent_image_studio", "images": ["8", 0]}},
}


def _is_local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host in ("localhost",):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


class ComfyUIGenerator(ImageGenerator):
    name = "comfyui"

    def __init__(self, url: str | None = None, session: requests.Session | None = None):
        self._url = url
        self.session = session or requests.Session()

    @property
    def url(self) -> str | None:
        return (self._url or get_settings().comfyui_url or "").rstrip("/") or None

    def status(self) -> dict[str, Any]:
        how = ("Run ComfyUI locally (python main.py --listen 127.0.0.1) with a checkpoint whose license fits your "
               "use, then set IMAGE_STUDIO_COMFYUI_URL=http://127.0.0.1:8188")
        if not self.url:
            return {"available": False, "detail": "IMAGE_STUDIO_COMFYUI_URL is not set", "how_to_enable": how}
        if not _is_local(self.url):
            return {"available": False, "detail": "Only local/private ComfyUI URLs are allowed", "how_to_enable": how}
        try:
            r = self.session.get(f"{self.url}/object_info/CheckpointLoaderSimple", timeout=5)
            r.raise_for_status()
            info = r.json()
            models = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        except Exception as exc:
            return {"available": False, "detail": f"ComfyUI not reachable at {self.url}: {exc}", "how_to_enable": how}
        if not models:
            return {"available": False, "detail": "ComfyUI has no checkpoints installed", "how_to_enable": how}
        return {"available": True, "detail": f"ComfyUI at {self.url}", "models": models}

    def build_workflow(self, *, prompt: str, negative_prompt: str, width: int, height: int, seed: int, steps: int,
                       cfg: float, checkpoint: str) -> dict[str, Any]:
        import copy
        wf = copy.deepcopy(DEFAULT_WORKFLOW)
        wf["3"]["inputs"].update(seed=seed, steps=steps, cfg=cfg)
        wf["4"]["inputs"]["ckpt_name"] = checkpoint
        wf["5"]["inputs"].update(width=width, height=height)
        wf["6"]["inputs"]["text"] = prompt
        wf["7"]["inputs"]["text"] = negative_prompt
        return wf

    def generate(self, *, prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024,
                 seed: int | None = None, steps: int = 25, cfg: float = 6.5, timeout: float = 600.0):
        if not prompt.strip():
            raise ValidationError("prompt must not be empty")
        if not (64 <= width <= 4096 and 64 <= height <= 4096):
            raise ValidationError("width/height must be within 64..4096")
        width, height = width // 8 * 8, height // 8 * 8
        st = self.status()
        if not st["available"]:
            raise ProviderUnavailableError(st["detail"], hint=st.get("how_to_enable"))
        checkpoint = get_settings().comfyui_checkpoint or st["models"][0]
        if checkpoint not in st["models"]:
            raise ValidationError(f"Checkpoint '{checkpoint}' is not installed in ComfyUI",
                                  details={"installed": st["models"]})
        seed = int(seed if seed is not None else random.randint(0, 2**31 - 1))
        wf = self.build_workflow(prompt=prompt, negative_prompt=negative_prompt, width=width, height=height, seed=seed,
                                 steps=steps, cfg=cfg, checkpoint=checkpoint)
        client_id = uuid.uuid4().hex
        r = self.session.post(f"{self.url}/prompt", json={"prompt": wf, "client_id": client_id}, timeout=30)
        if r.status_code != 200:
            raise ProviderUnavailableError(f"ComfyUI rejected the workflow: {r.text[:400]}")
        prompt_id = r.json()["prompt_id"]
        deadline = time.monotonic() + timeout
        outputs = None
        while time.monotonic() < deadline:
            h = self.session.get(f"{self.url}/history/{prompt_id}", timeout=30)
            if h.status_code == 200 and prompt_id in h.json():
                entry = h.json()[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise ProviderUnavailableError(f"ComfyUI generation failed: {status}")
                outputs = entry.get("outputs")
                if outputs:
                    break
            time.sleep(1.0)
        if not outputs:
            raise ProviderUnavailableError("ComfyUI generation timed out")
        images = [img for node in outputs.values() for img in node.get("images", [])]
        if not images:
            raise ProviderUnavailableError("ComfyUI returned no images")
        img = images[0]
        v = self.session.get(f"{self.url}/view", params={"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                                          "type": img.get("type", "output")}, timeout=60)
        v.raise_for_status()
        with Image.open(io.BytesIO(v.content)) as im:
            rgba = np.asarray(im.convert("RGBA")).copy()
        meta = {"provider": "comfyui", "model": checkpoint, "seed": seed, "steps": steps, "cfg": cfg,
                "width": width, "height": height, "prompt_id": prompt_id,
                "note": "Check the model's license for your intended use."}
        return rgba, meta
