"""Agent integration files: canonical skill, synced copies, MCP configuration."""

import filecmp
import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _frontmatter(p: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    assert m, f"{p} has no front matter"
    return yaml.safe_load(m.group(1))


def test_canonical_skill_frontmatter():
    fm = _frontmatter(REPO / "skills" / "image-studio" / "SKILL.md")
    assert fm["name"] == "image-studio"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fm["name"])
    assert 50 < len(fm["description"]) <= 1024


def test_skill_copies_in_sync():
    src = REPO / "skills" / "image-studio"
    for target in (REPO / ".claude" / "skills" / "image-studio", REPO / ".agents" / "skills" / "image-studio"):
        cmp = filecmp.dircmp(src, target)
        stack = [cmp]
        while stack:
            c = stack.pop()
            assert not (c.left_only or c.right_only or c.diff_files), \
                f"{target} is out of sync; run `image-studio install-skills`"
            stack.extend(c.subdirs.values())


def test_skill_references_exist():
    text = (REPO / "skills" / "image-studio" / "SKILL.md").read_text()
    for ref in re.findall(r"\((references/[^)]+)\)", text):
        assert (REPO / "skills" / "image-studio" / ref).exists(), ref


def test_skill_mentions_only_real_tools():
    from image_studio.mcp_server.server import create_server
    names = set(create_server()._image_studio_tools)
    text = "".join(p.read_text() for p in (REPO / "skills").rglob("*.md"))
    used = set(re.findall(r"`([a-z_]+)`", text))
    candidates = {u for u in used if "_" in u and (u.startswith(("get_", "create_", "add_", "render_", "view_",
                                                                   "export_", "search_", "save_", "fetch_",
                                                                   "record_", "inspect_", "analyze_",
                                                                   "submit_", "draft_", "complete_", "apply_",
                                                                   "adjust_", "match_", "remove_", "edit_",
                                                                   "import_", "duplicate_", "transform_")))}
    unknown = candidates - names
    assert not unknown, f"skills mention tools that do not exist: {unknown}"


def test_mcp_json():
    data = json.loads((REPO / ".mcp.json").read_text())
    srv = data["mcpServers"]["image-studio"]
    assert srv["args"][-1] == "serve"
