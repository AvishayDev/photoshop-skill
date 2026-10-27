# Agent instructions (Codex and other AGENTS.md-aware agents)

This repository is **Agent Image Studio**: an MCP server + skills for creating and editing images.

## When the user asks for an image to be created or edited

Use the `image-studio` skill (`.agents/skills/image-studio/SKILL.md`) and the `image-studio` MCP
server. Non-negotiable:

1. Before modifying any image, present a numbered plan with **at least 10 meaningful, request-specific
   steps**, then register it with `submit_plan` (the server enforces this). Proceed without asking for
   approval unless a decision genuinely needs the user.
2. Search the knowledge base (`search_knowledge`) before researching; research references when
   real-world appearance matters; respect licenses.
3. Edit non-destructively (locked originals, layers, masks, adjustment layers, checkpoints).
4. Render previews and actually look at them; fix defects; don't claim success from tool results alone.
5. Deliver export path, editable project path, limitations and attribution; save reusable knowledge.

## When working on the code

- Python package in `src/image_studio`; tests in `tests/` (`pytest`); lint with `ruff check src tests`.
- Canonical skills live in `skills/`; run `image-studio install-skills` after editing them.
- Regenerate `docs/editing-tools.md` with `python scripts/gen_tool_docs.py` after changing tools.
- Never commit `projects/`, caches, credentials or downloaded images.
