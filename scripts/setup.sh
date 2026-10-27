#!/usr/bin/env bash
# One-shot setup for macOS/Linux: virtualenv, package, skills, diagnostics.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -e ".[dev]"
image-studio install-skills --agent both >/dev/null
image-studio doctor || true
echo
echo "Next: register the MCP server with your agent:"
echo "  claude mcp add image-studio --scope project -- $(command -v image-studio) serve"
echo "  codex mcp add image-studio -- $(command -v image-studio) serve"
