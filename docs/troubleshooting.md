# Troubleshooting

Start with `image-studio doctor` (add `--network` to test research providers, `--gimp-filters` to
start GIMP).

| Symptom | Cause / fix |
| --- | --- |
| `plan_required` error on every edit | Intended. Show the user a 10+ step plan and call `submit_plan` first. Scripts can set `IMAGE_STUDIO_REQUIRE_PLAN=0`. |
| `Plan rejected: ...` | Fewer than 10 steps, steps under 4 words, near-duplicate padding, or no step about inspecting/verifying or saving/exporting. |
| `backend gimp: GIMP executable not found` | Install GIMP 3 or set `IMAGE_STUDIO_GIMP` (AppImage path, `flatpak run org.gimp.GIMP`). |
| `GIMP 2.x found` | GIMP 2.10 is not supported (Python 2 plug-ins). Install GIMP 3 (Flatpak/AppImage on older distros). |
| GIMP job times out | First start builds font caches (can take >60 s). Raise `IMAGE_STUDIO_GIMP_TIMEOUT`. |
| AppImage fails (FUSE) | Extract: `./GIMP.AppImage --appimage-extract`, use `squashfs-root/AppRun`. |
| `path_not_allowed` | Tools only read the workspace, CWD and `IMAGE_STUDIO_ALLOWED_DIRS`; they only write the workspace and `IMAGE_STUDIO_OUTPUT_DIRS`. |
| `research_failed ... HTTP 429` | Provider rate limit. Wait, use fewer/more specific queries, try the other provider, or use `size='large'` instead of `full` on Wikimedia. |
| Wrong/irrelevant search hits | Use specific queries ("Pavo cristatus male side view", "peacock standing"), and try both providers. |
| MCP server not visible in Claude Code | `claude mcp list`; approve the project `.mcp.json`; ensure `image-studio` is on PATH (or use the absolute path from `image-studio mcp-config`). |
| Codex tool calls time out | Increase `tool_timeout_sec` in `config.toml` (GIMP and research calls can take > 60 s). |
| Layer is "locked" | Opened originals are protected. `duplicate_layer` and edit the copy. |
| Colour looks different in GIMP/Photoshop | Blend modes follow W3C formulas; GIMP's default (perceptual/linear) modes differ slightly. The project file is the reference. |
| Project corrupted / blob missing | `restore_checkpoint` or `restore_revision`; revisions are in `revisions/`. |
| Disk usage grows | Each revision keeps its blobs. `Project.garbage_collect()` removes blobs no revision references; `IMAGE_STUDIO_MAX_REVISIONS` (default 100). |
