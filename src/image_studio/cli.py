"""Command-line interface: diagnostics, MCP server, skills installation and common operations."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import find_repo_root, get_settings


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ----- doctor ---------------------------------------------------------------------------------

def cmd_doctor(args) -> int:
    from .core.capabilities import capability_report
    from .knowledge.storage import KnowledgeStore
    from .knowledge.validation import validate_entry

    s = get_settings()
    ok = True
    lines: list[tuple[str, str, str]] = []

    def check(label: str, status: str, detail: str = ""):
        lines.append((status, label, detail))

    check("Python", "ok" if sys.version_info >= (3, 10) else "fail", platform.python_version())
    for mod in ("numpy", "PIL", "cv2", "pydantic", "yaml", "requests", "mcp"):
        try:
            m = __import__(mod)
            check(f"package {mod}", "ok", getattr(m, "__version__", ""))
        except ImportError as exc:
            ok = False
            check(f"package {mod}", "fail", str(exc))
    from .mcp_server.compat import SDK_MAJOR
    check("MCP SDK API", "ok", f"major {SDK_MAJOR}")
    rep = capability_report(check_gimp_filters=args.gimp_filters)
    for name, st in rep["backends"].items():
        status = "ok" if st["available"] else ("info" if name != "gimp" else "warn")
        detail = (st.get("version") or "") + (" " + st["detail"] if st.get("detail") else "")
        if not st["available"] and st.get("how_to_enable"):
            detail += f"\n      -> {st['how_to_enable']}"
        if not st.get("verified", True):
            detail += " [unverified in CI]"
        check(f"backend {name}", status, detail.strip())
    if args.gimp_filters and "gimp_gegl_operations" in rep:
        check("GIMP GEGL operations", "ok", str(len(rep["gimp_gegl_operations"])))
    from .patterns import PatternLibrary
    pats = PatternLibrary().all()
    check("pattern library", "ok" if pats else "warn", f"{len(pats)} learned/authored patterns")
    try:
        s.workspace.mkdir(parents=True, exist_ok=True)
        probe = s.workspace / ".write_test"
        probe.write_text("x")
        probe.unlink()
        check("workspace", "ok", str(s.workspace))
    except OSError as exc:
        ok = False
        check("workspace", "fail", f"{s.workspace}: {exc}")
    store = KnowledgeStore()
    entries = store.all()
    errors = sum(1 for e in entries for p in validate_entry(e) if p["level"] == "error")
    check("knowledge base", "ok" if entries and not errors else "warn",
          f"{store.root} ({len(entries)} entries, {errors} errors)")
    check("plan gate", "ok", "enforced" if s.require_plan else "DISABLED (IMAGE_STUDIO_REQUIRE_PLAN=0)")
    if args.network:
        from .research.search import ResearchService
        svc = ResearchService()
        for prov in ("wikimedia_commons", "openverse"):
            try:
                n = len(svc.provider(prov).search("tiger", limit=2))
                check(f"research {prov}", "ok" if n else "warn", f"{n} results")
            except Exception as exc:
                check(f"research {prov}", "warn", str(exc)[:200])
    symbols = {"ok": "[ok]  ", "warn": "[warn]", "fail": "[FAIL]", "info": "[info]"}
    print(f"agent-image-studio {__version__} diagnostics\n")
    for status, label, detail in lines:
        print(f"{symbols[status]} {label}: {detail}")
    print("\nCore editing works without GIMP; GIMP 3 adds native GEGL filters, clone/heal tools and .xcf files.")
    return 0 if ok else 1


# ----- skills & MCP config ------------------------------------------------------------------------

def _repo() -> Path:
    root = find_repo_root(Path.cwd()) or find_repo_root()
    if not root:
        raise SystemExit("Run this from a clone of the agent-image-studio repository")
    return root


def sync_skills(repo: Path, targets: list[Path]) -> list[str]:
    src = repo / "skills"
    copied = []
    for target in targets:
        for skill in sorted(p for p in src.iterdir() if (p / "SKILL.md").exists()):
            dest = target / skill.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill, dest)
            copied.append(str(dest))
    return copied


def cmd_install_skills(args) -> int:
    repo = _repo()
    targets: list[Path] = []
    base = Path.home() if args.user else repo
    if args.agent in ("claude", "both"):
        targets.append(base / ".claude" / "skills")
    if args.agent in ("codex", "both"):
        targets.append(base / ".agents" / "skills")
    for t in targets:
        t.mkdir(parents=True, exist_ok=True)
    _print({"installed": sync_skills(repo, targets), "source": str(repo / "skills")})
    return 0


def _server_command() -> tuple[str, list[str]]:
    exe = shutil.which("image-studio")
    if exe:
        return exe, ["serve"]
    return sys.executable, ["-m", "image_studio.cli", "serve"]


def cmd_mcp_config(args) -> int:
    cmd, cargs = _server_command()
    repo = find_repo_root(Path.cwd()) or find_repo_root()
    env = {"IMAGE_STUDIO_WORKSPACE": str((repo or Path.cwd()) / "projects")}
    if args.agent == "claude":
        print("# Project scope (.mcp.json in the repository root):")
        _print({"mcpServers": {"image-studio": {"command": cmd, "args": cargs, "env": env}}})
        print("\n# Or register with the CLI:")
        print(f"claude mcp add image-studio --scope project -e IMAGE_STUDIO_WORKSPACE={env['IMAGE_STUDIO_WORKSPACE']} "
              f"-- {cmd} {' '.join(cargs)}")
    else:
        print("# ~/.codex/config.toml (or .codex/config.toml in a trusted project):")
        print("[mcp_servers.image-studio]")
        print(f"command = {json.dumps(cmd)}")
        print(f"args = {json.dumps(cargs)}")
        print("startup_timeout_sec = 30")
        print("tool_timeout_sec = 300")
        print("[mcp_servers.image-studio.env]")
        print(f"IMAGE_STUDIO_WORKSPACE = {json.dumps(env['IMAGE_STUDIO_WORKSPACE'])}")
        print("\n# Or register with the CLI:")
        print(f"codex mcp add image-studio --env IMAGE_STUDIO_WORKSPACE={env['IMAGE_STUDIO_WORKSPACE']} -- "
              f"{cmd} {' '.join(cargs)}")
    return 0


# ----- operations ---------------------------------------------------------------------------------

def _editor():
    from .editor import Editor
    return Editor()


def cmd_projects(args) -> int:
    _print(_editor().list_projects())
    return 0


def cmd_new(args) -> int:
    w, h = (int(v) for v in args.size.lower().split("x"))
    _print(_editor().create_project(args.name, w, h, args.background))
    return 0


def cmd_open(args) -> int:
    _print(_editor().open_document(args.path, args.name))
    return 0


def cmd_info(args) -> int:
    _print(_editor().get_document_info(args.document_id))
    return 0


def cmd_render(args) -> int:
    _print(_editor().render_preview(args.document_id, args.max_size))
    return 0


def cmd_export(args) -> int:
    _print(_editor().export_image(args.document_id, args.output, args.format, args.quality))
    return 0


def cmd_save(args) -> int:
    _print(_editor().save_document(args.document_id, args.format, args.output))
    return 0


def cmd_kb(args) -> int:
    from .knowledge.retrieval import search_knowledge
    from .knowledge.storage import KnowledgeStore
    from .knowledge.validation import validate_entry
    store = KnowledgeStore()
    if args.kb_cmd == "search":
        _print(search_knowledge(args.query, args.limit, store))
    elif args.kb_cmd == "list":
        for e in store.all():
            print(f"{e.path:45s} {e.confidence:7s} {e.reviewed}  {e.title}")
    elif args.kb_cmd == "validate":
        bad = 0
        for e in store.all():
            for p in validate_entry(e):
                print(f"{p['level']:8s} {e.path}: {p['message']}")
                bad += p["level"] == "error"
        print(f"{len(store.all())} entries checked, {bad} errors")
        return 1 if bad else 0
    return 0


def cmd_research(args) -> int:
    from .research.search import ResearchService
    _print(ResearchService().search(args.query, args.provider, args.limit, args.reusable_only))
    return 0


def cmd_plan(args) -> int:
    from .workflows.planning import draft_plan
    d = draft_plan(args.request)
    print(f"Request type: {d['request_type']}\n")
    for i, s in enumerate(d["steps"], 1):
        print(f"{i:2d}. {s}")
    return 0


def cmd_serve(args) -> int:
    from .mcp_server.server import main
    main(args.transport)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="image-studio", description="Open-source Photoshop-style toolkit for AI agents")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Check installation, backends and providers")
    d.add_argument("--network", action="store_true", help="Also test research providers online")
    d.add_argument("--gimp-filters", action="store_true", help="Start GIMP and count GEGL operations")
    d.set_defaults(func=cmd_doctor)

    s = sub.add_parser("serve", help="Run the MCP server (stdio)")
    s.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http", "sse"])
    s.set_defaults(func=cmd_serve)

    i = sub.add_parser("install-skills", help="Copy the canonical skills to Claude Code / Codex skill folders")
    i.add_argument("--agent", choices=["claude", "codex", "both"], default="both")
    i.add_argument("--user", action="store_true", help="Install to ~/.claude/skills and ~/.agents/skills")
    i.set_defaults(func=cmd_install_skills)

    m = sub.add_parser("mcp-config", help="Print MCP configuration for an agent")
    m.add_argument("--agent", choices=["claude", "codex"], default="claude")
    m.set_defaults(func=cmd_mcp_config)

    sub.add_parser("projects", help="List projects").set_defaults(func=cmd_projects)
    n = sub.add_parser("new", help="Create a project")
    n.add_argument("name")
    n.add_argument("--size", default="1600x1000")
    n.add_argument("--background", default="#ffffff")
    n.set_defaults(func=cmd_new)
    o = sub.add_parser("open", help="Open an image/ora/xcf/project")
    o.add_argument("path")
    o.add_argument("--name")
    o.set_defaults(func=cmd_open)
    for name, fn in (("info", cmd_info), ("render", cmd_render)):
        c = sub.add_parser(name)
        c.add_argument("document_id")
        if name == "render":
            c.add_argument("--max-size", type=int, default=1024)
        c.set_defaults(func=fn)
    e = sub.add_parser("export", help="Export a document")
    e.add_argument("document_id")
    e.add_argument("--format", default="png")
    e.add_argument("--output")
    e.add_argument("--quality", type=int, default=92)
    e.set_defaults(func=cmd_export)
    sv = sub.add_parser("save", help="Save native layered file")
    sv.add_argument("document_id")
    sv.add_argument("--format", default="ora", choices=["project", "ora", "xcf", "psd"])
    sv.add_argument("--output")
    sv.set_defaults(func=cmd_save)

    k = sub.add_parser("kb", help="Knowledge base")
    ksub = k.add_subparsers(dest="kb_cmd", required=True)
    ks = ksub.add_parser("search")
    ks.add_argument("query")
    ks.add_argument("--limit", type=int, default=8)
    ksub.add_parser("list")
    ksub.add_parser("validate")
    k.set_defaults(func=cmd_kb)

    r = sub.add_parser("research", help="Search reference images")
    r.add_argument("query")
    r.add_argument("--provider", action="append")
    r.add_argument("--limit", type=int, default=6)
    r.add_argument("--reusable-only", action="store_true")
    r.set_defaults(func=cmd_research)

    pp = sub.add_parser("pipeline", help="Painting pipelines (declarative JSON specs)")
    psub = pp.add_subparsers(dest="pipeline_cmd", required=True)
    pr = psub.add_parser("run", help="Run a pipeline spec .json (Python pipelines: run them with python)")
    pr.add_argument("spec")
    psub.add_parser("actions", help="List painting actions and parameters")
    pp.set_defaults(func=cmd_pipeline)

    pt = sub.add_parser("patterns", help="Pattern library (learned visual patterns)")
    ptsub = pt.add_subparsers(dest="patterns_cmd", required=True)
    pts = ptsub.add_parser("search")
    pts.add_argument("query")
    pts.add_argument("--kind")
    ptsub.add_parser("list")
    ptl = ptsub.add_parser("learn", help="Learn patterns from a local image file")
    ptl.add_argument("image")
    ptl.add_argument("--name", required=True)
    ptl.add_argument("--rect", nargs=4, type=int, metavar=("X", "Y", "W", "H"))
    pt.set_defaults(func=cmd_patterns)

    pl = sub.add_parser("plan", help="Draft a >=10-step plan for a request")
    pl.add_argument("request")
    pl.set_defaults(func=cmd_plan)
    return p


def cmd_pipeline(args) -> int:
    from .pipeline.spec import describe_actions, run_spec

    if args.pipeline_cmd == "actions":
        _print(describe_actions())
        return 0
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    _print(run_spec(spec, verbose=True))
    return 0


def cmd_patterns(args) -> int:
    from .patterns import PatternLibrary, learn_from_image

    lib = PatternLibrary()
    if args.patterns_cmd == "search":
        _print(lib.search(args.query, args.kind))
    elif args.patterns_cmd == "list":
        _print([e.summary() for e in lib.all()])
    else:
        from .editor.base import load_rgba
        rgba, _ = load_rgba(Path(args.image))
        _print(learn_from_image(rgba, rect=args.rect, name=args.name))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from .errors import StudioError
    try:
        return int(args.func(args) or 0)
    except StudioError as exc:
        _print(exc.to_dict())
        return 2


if __name__ == "__main__":
    sys.exit(main())
