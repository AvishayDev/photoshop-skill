# Agent Image Studio — your AI agent paints images itself, with Photoshop-style tools

Agent Image Studio lets AI coding agents such as **Claude Code** and **Codex** create images **from
scratch without any generative AI model**, and edit existing images with real editing tools. You say
*"create a tiger in a forest, realism style"*; the agent:

1. splits the work into **at least 10 easy, clear steps** (enforced),
2. checks its **pattern library** - what it already learned in earlier tasks,
3. **researches the internet**: what a tiger looks like, its stripe layout, how forests are structured,
   how light falls through a canopy,
4. **learns patterns from reference photos** - silhouette ("borders"), stripe period and coverage,
   palette, light direction - and **saves them to the repo** so it never has to learn them again,
5. **paints the image itself** as a Python pipeline of Photoshop-like actions: gradients, brushes,
   pattern fills, scatter-leaf foliage, fur strokes, perspective water, light rays, shadows,
   reflections, clone-stamp texture synthesis, adjustment layers,
6. looks at the previews, fixes defects, and exports a PNG/JPEG plus the editable layered project.

```bash
python pipelines/tiger_in_forest.py     # "Create a tiger in a forest, realism style"
python pipelines/peacock_in_ocean.py    # "Create a peacock in the ocean" (the 18-step plan from the brief)
```

- **Free and open source** (Apache-2.0). No paid API, no cloud service, no generative model.
- **Painting engine** (`image_studio.paint`): sky, sun, clouds, mountains, ground, ocean, forest, grass,
  figures (data-driven subjects), stripes/spots/eyespots/scales, form shading, fur, light, finishing.
- **Pattern learning + library** (`image_studio.patterns`, `knowledge/patterns/`): measured textures,
  palettes, silhouettes and subject recipes, version-controlled and reused across tasks.
- **Pipelines** (`image_studio.pipeline`): plan-gated, every element a named layer of a real project.
- **MCP server** with 101 structured tools (painting, pattern learning, layers, masks, selections,
  clone/heal, filters, adjustment layers, text, shadows, reflections, research, export).
- **GIMP 3** as an optional native engine for editing photos (GEGL filters, native clone/heal, `.xcf`).
- **Agent skill** for Claude Code (`.claude/skills`) and Codex (`.agents/skills`) from one canonical source.
- **Visual research** through free, licensed sources (Wikimedia Commons, Openverse) plus web search,
  with license checks and attribution tracking.

Painted results are honest painterly/illustrative realism, not photographs - see
[docs/painting.md](docs/painting.md#limits-be-honest-with-users).

## How it works

```
You: "Create a peacock in the ocean."
Agent (with the image-studio skill):
  1. numbered plan of >= 10 steps (shown to you, validated by Pipeline / submit_plan)
  2. search_patterns / search_knowledge     - reuse figure/peacock-standing, texture/peacock-eyespot ...
  3. web research + search_references / fetch_reference / view the images
  4. learn_pattern (palette, markings, period, silhouette) -> save_pattern
  5. write pipelines/peacock_in_the_ocean.py: sky -> clouds -> sun -> ocean -> peacock figure ->
     water surface over the feet -> rim light -> ripples -> reflection -> grade -> vignette -> grain
  6. run it, open every preview, fix, re-run
  7. exports + layered .ora + pipeline.json; report; save improved patterns/knowledge
```

Editing photos uses the same plan → research → inspect loop with the layer tools (masks, clone stamp,
heal, background removal, adjustment layers, shadows, reflections) - see
[`examples/peacock_in_the_ocean.py`](examples/peacock_in_the_ocean.py) for a photo-compositing example
driven over MCP (assets: peacock photo by Ksheera Piraati, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0);
ocean plate CC0 via Openverse).

Everything is stored in a project folder (`projects/<name>/`): `project.json` (document, layer tree,
history, checkpoints), content-addressed pixel blobs, revisions, original assets, references with
provenance, research notes, plans, previews and exports.

## Quick start

```bash
git clone https://github.com/avishaydev/photoshop-skill.git && cd photoshop-skill
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
image-studio doctor                                        # shows what is available
```

Optional: install **GIMP 3** (https://www.gimp.org/downloads/) and run `image-studio doctor` again.
If it isn't found automatically, set `IMAGE_STUDIO_GIMP` (see [docs/installation.md](docs/installation.md)).

### Connect your agent

**Claude Code** — the repo includes `.mcp.json` and `.claude/skills/image-studio/`. Open the folder in
Claude Code and approve the `image-studio` server, or:

```bash
claude mcp add image-studio --scope project -- image-studio serve
```

**Codex** — the repo includes `.agents/skills/image-studio/` and `AGENTS.md`. Register the server:

```bash
codex mcp add image-studio -- image-studio serve
```

`image-studio mcp-config --agent claude|codex` prints configs with absolute paths, and
`image-studio install-skills --user` installs the skill for use in other projects.
Details: [docs/agent-setup.md](docs/agent-setup.md).

### Ask for an image

> Create a photorealistic tiger standing in a dense forest at sunrise.

> Edit `~/Pictures/street.jpg` to make the lighting look cinematic.

> Continue editing the "Peacock in the Ocean" project and make the reflection calmer.

Outputs land in `projects/<project-name>/`:

| What | Where |
| --- | --- |
| Final image | `exports/<name>.png` / `.jpg` / `.webp` (+ `.credits.json` with sources and licenses) |
| Editable master | the project folder itself (`project.json` + `blobs/`); reopen with `open_document` |
| Layered file for GIMP & co. | `exports/<name>.xcf` (GIMP 3) or `exports/<name>.ora` (OpenRaster, always) |
| Previews | `previews/` |
| Research | `references/` (+ provenance JSON), `research/notes.json`, contact sheets |

## What it can do

| Area | Operations |
| --- | --- |
| Documents | create/open (PNG, JPEG, WebP, TIFF, ORA; XCF/PSD via GIMP), save project/ORA/XCF/PSD*, checkpoints, undo, history, crop, resize image/canvas |
| Layers | raster, text, shape, fill/gradient, procedural, group, adjustment layers; duplicate, delete, reorder, group, merge, flatten (explicit only), opacity, visibility, 20 blend modes, clipping masks, lock |
| Transforms | move, scale, rotate, shear, flip, perspective (4-corner), align; smart re-rendering from originals |
| Selections & masks | rectangle/ellipse/polygon, by colour / magic wand, from layer alpha, grow/shrink/feather/invert; masks from selection/alpha/luminance/gradients, paint, refine, apply |
| Retouching | clone stamp (aligned/non-aligned, sample layer/merged), healing & spot healing, object removal (inpainting), background removal (GrabCut, colour key, optional rembg) |
| Colour | brightness/contrast, levels, curves, hue/saturation, colour balance, exposure, vibrance, temperature/tint, photo filter, channel mixer, B&W, invert, posterize, threshold, statistical colour matching |
| Filters | 17 built-in (blurs, unsharp mask, high-pass, noise/grain, denoise, vignette, bloom, tilt-shift, ripple, ...) plus 130+ GEGL operations through GIMP |
| Compositing | drop shadow / outer glow / stroke effects, cast shadows and contact shadows from the light direction, water reflections, point/directional light, god rays, rim light |
| Inspection | previews (full, region, solo layer), image statistics and defect heuristics, image/revision comparison with heatmaps, subject-vs-scene integration analysis |
| Research & knowledge | Wikimedia Commons, Openverse, local folders; license assessment; reference analysis; observations; knowledge search/save |
| Painting from scratch | sky, sun, clouds, mountains, ground, ocean, forest/foliage, grass, figures, stripes/spots/eyespots/scales, fur, rays, haze, dapples, vignette, grain; pipelines (Python + JSON) |
| Pattern learning | palette, stripes/spots (period, coverage, elongation), texture direction, light direction, silhouette contour; JSON pattern library; clone-stamp texture synthesis |

\* PSD export needs a local Photoshop (optional, unverified in CI).

Full tool reference: [docs/editing-tools.md](docs/editing-tools.md) (generated from the server).

## Costs

Nothing is paid. The painting engine, GIMP, the Python stack, Wikimedia Commons and Openverse are free.
Photoshop (optional, for .psd export) needs your own licence; image providers have rate limits.

## Limitations (read this)

- **Painted, not photographed**: subjects are painted from figure recipes and learned patterns. They
  read well at medium distance; close-up anatomy (faces, eyes, hands) is simplified. A new kind of
  subject needs a figure recipe the first time (then it is reused from the library).
- Pattern learning uses GrabCut for silhouettes; shadowed limbs may need `fg_points`. Image providers
  can rate-limit; the agent then relies on the library and web descriptions.
- Background removal uses GrabCut / colour keying; difficult edges (hair, similar colours such as a
  green peacock train on grass) need mask refinement (seed points, painted masks). Optional `rembg`
  helps.
- 8-bit sRGB documents only (high-bit-depth and CMYK inputs are converted).
- GIMP is used through headless batch jobs (~2-4 s start-up per native operation). GIMP 2.10 is not
  supported. Native-format exports bake adjustment layers and effects into raster layers; ORA bakes
  masks into alpha (XCF keeps them).
- The Photoshop adapter is implemented against its documented local API but was not exercised against a
  real installation in CI.
- Visual inspection metrics are heuristics; the agent must still look at the previews.
- License assessment is conservative and not legal advice.

## Documentation

- [docs/installation.md](docs/installation.md) — install, GIMP setup, environment variables, platforms
- [docs/agent-setup.md](docs/agent-setup.md) — Claude Code and Codex configuration
- [docs/architecture.md](docs/architecture.md) — design, backends, extension points
- [docs/editing-tools.md](docs/editing-tools.md) — every MCP tool and parameter
- [docs/research.md](docs/research.md) — providers, licensing, research workflow
- [docs/painting.md](docs/painting.md) — painting from scratch, pipelines, pattern learning and library
- [docs/troubleshooting.md](docs/troubleshooting.md)
- [docs/asset-policy.md](docs/asset-policy.md) — what (not) to commit, Git LFS
- [knowledge/README.md](knowledge/README.md) — the knowledge base format

## Development

```bash
pip install -e ".[dev]"
pytest                       # unit + integration (GIMP tests skip without GIMP 3)
IMAGE_STUDIO_GIMP=/path/to/gimp pytest -m gimp
ruff check src tests
python scripts/gen_tool_docs.py   # after changing tools
image-studio install-skills       # after editing skills/
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Code: Apache-2.0. Knowledge-base text: written for this project; cited sources keep their own
licenses. The repository contains no images; painted outputs stay in your local `projects/` folder.
