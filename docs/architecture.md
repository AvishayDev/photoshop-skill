# Architecture

```
            Claude Code / Codex  (skills: .claude/skills, .agents/skills  <- canonical skills/)
                         │  MCP (stdio, JSON-RPC)
                         ▼
   ┌──────────────── image_studio.mcp_server ────────────────┐
   │ 101 structured tools · plan gate · structured errors     │
   └───────┬────────────┬──────────────┬─────────────┬────────┘
           ▼            ▼              ▼             ▼
      editor/       research/      knowledge/    workflows/
   (operations)  (providers,      (markdown KB,  (planning, quality
        │         licensing,       BM25 search,   checks, integration
        │         analysis)        validation)    analysis)
        ▼
      core/  document & layer model · project store · compositor · raster engine
        │
        ▼
   backends/  pillow (built-in, always) · gimp (GIMP 3 batch bridge) · photoshop (optional)

   paint/      procedural painting engine (brushes, shapes, shading, patterns, scenes, figures,
               finishing, texture synthesis) - creates pixels from scratch, no generative model
   patterns/   pattern learning from references + JSON pattern library (knowledge/patterns/)
   pipeline/   Pipeline (Python API, plan-gated, layered output) + declarative JSON specs
```

**Creating images = painting, not generating.** A request is decomposed into a plan, references are
studied and *measured* (`patterns.learn`), and the agent writes a pipeline of painting actions
(`paint.*`) that renders each element - sky, water, forest, figure, shadows, reflections, grade - as a
named layer of a normal project. Learned parameters and subject recipes are stored as JSON in
`knowledge/patterns/` so the next task starts from them. See [painting.md](painting.md).

## Key decisions

**The document model is the source of truth, not any editor.** `core.document.Document` holds the
canvas, a layer tree (`root` + group `children`, bottom-to-top), assets with provenance, the active
selection and metadata. Layers (`core.layer.Layer`) carry stable ids, kind (raster, text, shape, fill,
group, adjustment), position/size, visibility, opacity, blend mode, mask, clipping, parent group,
parametric properties (text/shape/fill/adjustment), non-destructive effects, a "smart" transform,
source asset and backend metadata. Keeping this model independent of GIMP means every feature works
without GIMP, and GIMP/Photoshop become *exporters, importers and operation providers*.

**Pixels live in content-addressed blobs.** Layer pixels and masks are immutable PNG files named by
the hash of their array (`core.blobstore`). The manifest only references hashes, so:
- a document with many layers is cheap to load (pixels decode lazily, with a small LRU cache);
- every revision snapshot and checkpoint is a small JSON file - undo never copies pixels;
- masks are separate 8-bit grayscale blobs; layers are RGBA. The document is *not* a stack of arrays.

**Atomic transactions.** Every mutating operation runs inside `Project.transaction`: it edits a deep
copy of the document, and only on success writes the new revision and replaces `project.json` with
`os.replace`. A failing operation leaves the project untouched. Revisions enable `undo`,
`restore_revision` and named checkpoints; restores are themselves revisions (undoable).

**Compositor.** `core.compositor` renders the tree with W3C compositing/blend formulas, isolated or
pass-through groups, masks, clipping masks, adjustment layers (applied to the backdrop) and layer
effects (drop shadow, outer glow, stroke). Layers are blended only inside their bounding boxes.

**Smart transforms.** Imported/scaled/rotated layers keep their original pixels (`base_blob`) and a
3x3 matrix; each new transform composes the matrix and re-renders once from the original, so repeated
adjustments don't degrade quality. Direct pixel edits bake the transform (with a warning).

**Non-destructive by default.** Opened photos become a locked `Original` layer (+ the untouched file in
`assets/`). Background removal produces masks; colour work is offered as (clipped) adjustment layers;
shadows, reflections and light are separate named layers; crops keep off-canvas pixels.

## Backends

| Backend | Status | Provides |
| --- | --- | --- |
| `pillow` (Pillow + NumPy + OpenCV) | always available | all core operations, 17 filters, clone/heal (Poisson), inpainting, GrabCut, OpenRaster read/write |
| `gimp` | GIMP 3.x; verified with 3.2.2 | 130+ GEGL filters, native clone (`gimp-clone`) and heal (`gimp-heal`), XCF write (layers, groups, masks, modes, opacity), XCF/PSD import |
| `photoshop` | optional; Windows COM / macOS AppleScript; **not verified in CI** | layered PSD export via ExtendScript |

### GIMP integration choice

GIMP 3 ships a Python 3 plug-in API (GObject Introspection) and a documented batch mode with a Python
interpreter: `gimp -i --batch-interpreter=python-fu-eval -b - --quit`. The backend starts a headless
GIMP process per job, passes a JSON job file, and the bridge script (`backends/gimp/bridge/gimp_bridge.py`)
executes operations from a fixed allow-list and writes `result.json`. Rationale:

- **Reliable and documented**: batch mode is a supported interface on Linux, macOS and Windows; no GUI
  automation, no undocumented plug-in IPC.
- **Secure**: no listening socket; the job file can only name allow-listed operations with
  validated parameters (GEGL operation names are checked against the installed list).
- **Cost**: ~2-4 s GIMP start-up per job, so GIMP is used where its native implementation matters,
  while bookkeeping and compositing stay in-process. A persistent bridge could remove the start-up
  cost later without changing the backend interface.
- GIMP 2.10 is detected but not supported (Python-Fu there is Python 2 only).

## Planning gate

`mcp_server.session.Session.check_plan` blocks every mutating tool until `submit_plan` accepted a plan
(`workflows.planning.validate_plan`: >= 10 steps, each >= 4 words, no near-duplicates, covering
understanding, action, verification and delivery). Plans are stored in each project's `plans/`.
`IMAGE_STUDIO_REQUIRE_PLAN=0` disables the gate for scripted, non-agent use.

## Extending

- **New operation**: add a method to an `editor/*Ops` mixin (inside `proj.transaction`), then a tool in
  `mcp_server/tools/`. Add tests. Agent-facing names and parameters are part of the API: add new tools
  or optional parameters rather than changing existing ones.
- **New backend**: subclass `backends.base.Backend`, advertise capabilities, register it in
  `core.capabilities.backends()`.
- **New research provider**: subclass `research.providers.base.ReferenceProvider` (search/get returning
  `ReferenceCandidate` with `LicenseInfo`) and add it to `ResearchService`.
- **New painting action**: add a builder to `paint/` (return a full-canvas float RGBA layer) and register it
  in `pipeline/spec.py` `ACTIONS`; it becomes available to `paint_layer` and `run_pipeline`.
- **New subject**: author a figure spec, render it alone, then save it as `figure/<name>` in the pattern
  library (`PatternLibrary().save`).
