# Connecting Claude Code and Codex

Install the package first (see [installation.md](installation.md)) so the `image-studio` command is
on your `PATH` (activate the virtualenv, or use the absolute path printed by `image-studio mcp-config`).

## Claude Code

Skills: Claude Code discovers project skills in `.claude/skills/<name>/SKILL.md`. This repository
ships `.claude/skills/image-studio/` (synced from the canonical `skills/` folder).

MCP server: the repository contains a project-scoped `.mcp.json`:

```json
{ "mcpServers": { "image-studio": { "command": "image-studio", "args": ["serve"] } } }
```

Open the repository in Claude Code and approve the project server when prompted, or register it
explicitly:

```bash
claude mcp add image-studio --scope project -- image-studio serve
# or for all projects:
claude mcp add image-studio --scope user -- /abs/path/.venv/bin/image-studio serve
```

`image-studio mcp-config --agent claude` prints a ready-to-paste config with absolute paths.
Use the skill from any other project by installing it user-wide: `image-studio install-skills --user --agent claude`
(copies to `~/.claude/skills/`).

## Codex

Skills: Codex discovers skills in `.agents/skills` (from the working directory up to the repository
root) and `~/.agents/skills`. This repository ships `.agents/skills/image-studio/`. `AGENTS.md` adds
the project rules.

MCP server:

```bash
codex mcp add image-studio -- image-studio serve
```

or in `~/.codex/config.toml` (or `.codex/config.toml` in a trusted project):

```toml
[mcp_servers.image-studio]
command = "image-studio"
args = ["serve"]
startup_timeout_sec = 30
tool_timeout_sec = 300     # GIMP jobs and research can take longer than the default
```

`image-studio mcp-config --agent codex` prints this with absolute paths. User-wide skill install:
`image-studio install-skills --user --agent codex` (copies to `~/.agents/skills/`).

## Keeping skills in sync

`skills/image-studio/` is canonical. After editing it run:

```bash
image-studio install-skills          # refreshes .claude/skills and .agents/skills
```

A unit test fails if the copies drift.

## First request

> Create a peacock standing in the ocean, with realistic water reflections.

The agent will check capabilities, show a 10+ step plan, research references, build the layered
composite, inspect previews, and deliver:

- editable project: `projects/<name>/` (`project.json` + blobs; reopen with `open_document`)
- layered interchange file: `projects/<name>/exports/<name>.ora` (and `.xcf` with GIMP)
- final image: `projects/<name>/exports/<name>.png` (+ `.credits.json`)
