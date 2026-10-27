# Agent instructions (Codex and other AGENTS.md-aware agents)

This repository is **Agent Image Studio**: an MCP server, a procedural painting engine and skills for
creating images from scratch (no generative AI - you paint them) and editing images.

## When the user asks for an image to be created or edited

Use the `image-studio` skill (`.agents/skills/image-studio/SKILL.md`) and the `image-studio` MCP
server. Non-negotiable:

1. Before modifying any image, present a numbered plan with **at least 10 meaningful, request-specific
   steps**, then register it with `submit_plan` (the server enforces this). Proceed without asking for
   approval unless a decision genuinely needs the user.
2. Search the pattern library (`search_patterns`) and knowledge base (`search_knowledge`) before
   researching; research on the internet when real-world appearance matters; measure references with
   `learn_pattern` and `save_pattern` what is reusable; respect licenses.
3. Create by painting: write `pipelines/<slug>.py` with `image_studio.pipeline.Pipeline` (or use
   `paint_layer` / `run_pipeline`). Never call an AI image generator unless the user asks for one.
   Edit non-destructively (locked originals, layers, masks, adjustment layers, checkpoints).
4. Render previews and actually look at them; fix defects; don't claim success from tool results alone.
5. Deliver export path, editable project path, pipeline script, limitations and attribution; save
   reusable patterns and knowledge.

## When working on the code

- Python package in `src/image_studio`; tests in `tests/` (`pytest`); lint with `ruff check src tests`.
- Canonical skills live in `skills/`; run `image-studio install-skills` after editing them.
- Regenerate `docs/editing-tools.md` with `python scripts/gen_tool_docs.py` after changing tools.
- Painting engine in `src/image_studio/paint`, pattern learning/library in `src/image_studio/patterns`,
  pipelines in `src/image_studio/pipeline`; example pipelines in `pipelines/`; pattern library JSON in
  `knowledge/patterns/`.
- Never commit `projects/`, caches, credentials or downloaded images.
