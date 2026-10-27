# Image generation (optional)

The core toolkit never requires a generative model or a paid API.

## Built-in procedural content (always available)

`create_procedural_layer`: clouds, fog, grain, bokeh, sky, water - seeded and reproducible; useful for
atmosphere, textures and backgrounds. Gradients via `create_fill_layer`; shapes and text are vector-
style parametric layers.

## Local ComfyUI provider

`generate_image_layer` talks to a ComfyUI server you run locally (https://github.com/comfyanonymous/ComfyUI)
through its HTTP API (`/object_info`, `/prompt`, `/history`, `/view`). It submits a standard
text-to-image workflow (CheckpointLoaderSimple -> CLIPTextEncode x2 -> EmptyLatentImage -> KSampler ->
VAEDecode -> SaveImage) and adds the result as a layer with provenance (model, seed, steps, cfg,
prompt). `mask_from_selection=true` masks the new layer to the current selection for inpaint-style
placement.

```bash
# in your ComfyUI checkout, with a checkpoint in models/checkpoints/
python main.py --listen 127.0.0.1 --port 8188
export IMAGE_STUDIO_COMFYUI_URL=http://127.0.0.1:8188
export IMAGE_STUDIO_COMFYUI_CHECKPOINT=<file name>   # optional; defaults to the first installed
image-studio doctor
```

Only loopback/private-network URLs are accepted, so prompts are not sent to remote services by accident.

### Hardware and licenses

- Diffusion models typically need a GPU with 6-24 GB VRAM (CPU works but is very slow).
- **Model licenses vary** (e.g. CreativeML OpenRAIL-M, Stability AI community licenses with revenue
  thresholds, non-commercial research licenses). Check the model card before commercial use. The
  provider records the checkpoint name in each generated asset's provenance.
- Status: implemented against the ComfyUI HTTP API; unit-tested with a mocked server. Not exercised
  against a real GPU in CI.

## Honest limits

Traditional compositing (masks, clone, heal, filters) cannot synthesize arbitrary new photorealistic
subjects. Without a generative provider the agent composites appropriately licensed photographs,
builds procedural/graphic elements, or explains the limitation and proposes alternatives.
