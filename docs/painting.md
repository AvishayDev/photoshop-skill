# Painting images from scratch

Agent Image Studio does **not** use generative AI to create images. The agent (Claude, Codex, ...)
plans the image, researches what things look like, measures patterns on reference photos, and then
paints the image itself through a pipeline of deterministic drawing operations - the same things an
artist does in Photoshop: gradients, soft brushes, shape paths, pattern fills, noise textures, clone
stamp quilting, light/shadow passes and colour grading.

```
request ─► plan (>= 10 steps) ─► pattern library / knowledge ─► web + image research
        ─► learn_pattern (palette, stripes/spots, period, silhouette, light) ─► save_pattern
        ─► pipelines/<slug>.py  (environment → subject figure → light/shadow/reflection → grade)
        ─► previews → look → fix → re-run ─► export PNG/JPEG + layered ORA + pipeline.json
```

## Try it

```bash
python pipelines/tiger_in_forest.py      # ~1 min
python pipelines/peacock_in_ocean.py     # ~25 s
```

Outputs go to `projects/<name>/` (exports, previews per stage, the layered project, `pipeline.json`).
Projects stay editable with every image-studio tool (`open_document` the project folder).

## The pieces

| Module | What it does |
| --- | --- |
| `paint.canvas` | colours, straight-alpha compositing, palette ramps |
| `paint.noise` | seeded fBm, domain warp, Worley cells, seamless tiles, ground-plane perspective mapping |
| `paint.shapes` | anti-aliased polygons (Catmull-Rom smoothed), ellipses, tapered/bent capsules, blobs |
| `paint.brush` | dab brush strokes (size, hardness, spacing, taper), directional fur, grass blades |
| `paint.shading` | height from silhouette → normals → wrap diffuse, ambient, rim, specular, occlusion |
| `paint.patterns` | stripes (warped, tapered, forking), spots/rosettes, eyespots, scales, bark |
| `paint.scene` | sky, sun, clouds, mountains, ground, ocean, trees, scatter-leaf foliage, forest, rays, haze, dapples |
| `paint.figure` | data-driven subjects: parts + materials + patterns + fur + details, lit by the key light |
| `paint.finish` | vignette, grain, colour washes, quick grade |
| `paint.synthesis` | patch-based texture synthesis (automated clone stamp) from a licensed exemplar |
| `patterns.learn` | measures palette, marks, period, orientation, light and silhouette on a reference |
| `patterns.library` | JSON pattern library in `knowledge/patterns/<kind>/<slug>.json` |
| `pipeline` | `Pipeline` Python API and declarative JSON specs (`run_spec`) |

## Python pipeline API (preferred)

```python
from image_studio.paint import scene, finish
from image_studio.patterns import PatternLibrary
from image_studio.pipeline import Pipeline

p = Pipeline("Create a tiger in a forest", plan=[...10+ steps...], size=(1600, 1000), seed=7)
with p.step(6):
    p.add("Sky", scene.sky(p.width, p.height, horizon_y=520, sun=(260, -120)), group="Environment")
with p.step(9):
    p.figure("Tiger", PatternLibrary().get("figure/tiger-walking").params, height=350, x=430,
             ground_y=880, facing="left", light_azimuth=150, light_elevation=45)
with p.step(10):
    p.contact_shadow("Tiger contact shadow", "Tiger")
    p.cast_shadow("Tiger cast shadow", "Tiger", azimuth=150, elevation=45, opacity=0.4)
    p.preview("subject")                       # open and look at this file
with p.step(15):
    p.finish()
```

`Pipeline` refuses plans with fewer than 10 meaningful steps (same validator as the MCP plan gate),
tags every layer with its plan step, and reports plan steps that were never executed.

## MCP tools

| Tool | Use |
| --- | --- |
| `list_paint_actions` | painting actions and their parameters |
| `paint_layer` | paint one action into an existing document (e.g. add light rays to a photo) |
| `run_pipeline` | build a whole image from a JSON spec |
| `learn_pattern` | measure patterns + silhouette on a fetched reference |
| `search_patterns` / `get_pattern` / `save_pattern` | the persistent pattern library |
| `synthesize_texture` | grow a texture from a licensed reference region (clone-stamp quilting) |

CLI: `image-studio pipeline run spec.json`, `image-studio pipeline actions`,
`image-studio patterns search|list|learn`.

## Pattern library

Entries are JSON with `params` (what the engine consumes), `learned` (raw measurements), `sources`
(url/title/license), `confidence` and `notes`. Kinds: `figure`, `texture`, `palette`, `silhouette`,
`scene`, `light`. Shipped entries include `figure/tiger-walking`, `figure/peacock-standing`,
`texture/tiger-stripes` (measured on a CC0 photo), `texture/peacock-eyespot`, palettes and a learned
tiger silhouette. Commit new entries so everyone who clones the repository benefits.

## Limits (be honest with users)

- Results are painterly/illustrative realism. They hold up at medium distance with good atmosphere and
  light; close-up anatomy (faces, hands, eyes) is simplified.
- New subject types need a figure recipe; the first one costs effort, later tasks reuse it.
- Rendering is CPU NumPy/OpenCV: a 1600x1000 scene takes ~20-60 s.
- `synthesize_texture` and compositing reuse reference pixels and therefore need a licence that allows
  derivatives; `learn_pattern` only measures and works with any reference you may view.
