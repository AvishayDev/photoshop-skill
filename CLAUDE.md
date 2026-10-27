# Claude Code project notes

@AGENTS.md

- The `image-studio` skill lives in `.claude/skills/image-studio/` (synced from `skills/`).
- The MCP server is configured in `.mcp.json` (`image-studio serve`); run `image-studio doctor` if tools
  are missing.
- For image requests: plan (≥10 steps) → `search_patterns`/knowledge → web + image research →
  `learn_pattern` → write and run `pipelines/<slug>.py` (paint it yourself; no AI image generators) →
  open every preview → fix → export → report → `save_pattern` / `save_knowledge`.
