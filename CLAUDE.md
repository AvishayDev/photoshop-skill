# Claude Code project notes

@AGENTS.md

- The `image-studio` skill lives in `.claude/skills/image-studio/` (synced from `skills/`).
- The MCP server is configured in `.mcp.json` (`image-studio serve`); run `image-studio doctor` if tools
  are missing.
- For image requests: plan (≥10 steps, `submit_plan`) → knowledge → research → layered edits →
  `render_preview` + view the image → fix → export → report → `save_knowledge`.
