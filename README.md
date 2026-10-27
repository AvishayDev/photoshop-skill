# Agent Image Studio — open-source "Photoshop for agents"

Agent Image Studio lets AI coding agents such as **Claude Code** and **Codex** create and edit images
with real editing tools: layers, masks, selections, blend modes, transforms, clone/heal, filters,
adjustment layers, text, shadows, reflections and lighting. You describe the image; the agent plans,
researches visual references, builds an editable layered composition, inspects the previews, corrects
defects and delivers the final export together with the editable project.

- **Free and open source** (Apache-2.0). No paid API or cloud service is required.
- **GIMP 3** as the native editing engine (GEGL filters, native clone/heal, `.xcf` files), with a
  built-in Pillow/NumPy/OpenCV engine so everything also works without GIMP.
- **MCP server** with 94 structured tools, stable layer ids, validation and structured errors.
- **Agent skill** for Claude Code (`.claude/skills`) and Codex (`.agents/skills`) from one canonical source.
- **Mandatory planning**: mutating tools refuse to run until the agent has registered a plan of at least
  10 meaningful steps.
- **Visual research** through free, licensed sources (Wikimedia Commons, Openverse), with license
  checks and attribution tracking.
- **Persistent visual knowledge** in version-controlled markdown (`knowledge/`), searched before new
  research and extended after successful tasks.
- **Non-destructive** layered projects with history, undo, checkpoints and atomic, crash-safe saves.

Example: *"Create a peacock standing in the ocean, with realistic water reflections."* is produced
end-to-end through the MCP protocol by [`examples/peacock_in_the_ocean.py`](examples/peacock_in_the_ocean.py):
research → licensed assets → GrabCut mask + hand-refined mask → backlight colour match, rim light,
waterline, ripples, reflection, cast shadow → inspection → correction round → export. Run it locally
to generate the image (no images are stored in this repository). Assets it uses: peacock photo by
Ksheera Piraati, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0)
([source](https://commons.wikimedia.org/wiki/File:Peacock_standing_on_grassy_field_-_India.jpg));
ocean plate "View calm ocean horizon sandy", CC0 1.0 (via Openverse).

## How it works

```
You: "Remove the background from this photo and put the subject on a snowy mountain."
Agent (with the image-studio skill):
  1. get_capabilities            - what can this installation do?
  2. draft_plan → shows you a numbered plan (≥10 steps) → submit_plan
  3. search_knowledge            - reuse saved knowledge (snow light, background removal, ...)
  4. search_references / fetch_reference / view_image / record_observation
  5. open_document → duplicate_layer → remove_background (mask) → edit_layer_mask ...
  6. render_preview → view_image → analyze_layer_integration → fix → re-check
  7. save_document (xcf/ora) → export_png → verified file + credits
  8. complete_plan → save_knowledge (reusable lessons)
```

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
| Generation (optional) | local ComfyUI text-to-image layers with provenance |

\* PSD export needs a local Photoshop (optional, unverified in CI).

Full tool reference: [docs/editing-tools.md](docs/editing-tools.md) (generated from the server).

## Costs

Nothing is paid by default. GIMP, the Python stack, Wikimedia Commons and Openverse are free.
Optional components carry their own terms: Photoshop needs your own licence; generative models have
their own licences and hardware requirements; providers have rate limits.

## Limitations (read this)

- **Photorealistic synthesis of new subjects needs a source**: a licensed photograph or a local
  generative model. Compositing tools (masks, clone, heal, filters) cannot invent arbitrary realistic
  objects; the agent says so and offers alternatives.
- Background removal uses GrabCut / colour keying; difficult edges (hair, similar colours such as a
  green peacock train on grass) need mask refinement (seed points, painted masks). Optional `rembg`
  helps.
- 8-bit sRGB documents only (high-bit-depth and CMYK inputs are converted).
- GIMP is used through headless batch jobs (~2-4 s start-up per native operation). GIMP 2.10 is not
  supported. Native-format exports bake adjustment layers and effects into raster layers; ORA bakes
  masks into alpha (XCF keeps them).
- The Photoshop adapter and the ComfyUI provider are implemented against their documented local APIs
  but were not exercised against real installations in CI (ComfyUI is unit-tested with a fake server).
- Visual inspection metrics are heuristics; the agent must still look at the previews.
- License assessment is conservative and not legal advice.

## Documentation

- [docs/installation.md](docs/installation.md) — install, GIMP setup, environment variables, platforms
- [docs/agent-setup.md](docs/agent-setup.md) — Claude Code and Codex configuration
- [docs/architecture.md](docs/architecture.md) — design, backends, extension points
- [docs/editing-tools.md](docs/editing-tools.md) — every MCP tool and parameter
- [docs/research.md](docs/research.md) — providers, licensing, research workflow
- [docs/generation.md](docs/generation.md) — optional local generation
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
licenses. The repository contains no images; generated outputs stay in your local `projects/` folder.
