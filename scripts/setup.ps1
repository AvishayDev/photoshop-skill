# One-shot setup for Windows PowerShell: virtualenv, package, skills, diagnostics.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path .venv)) { py -3 -m venv .venv }
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
pip install -e ".[dev]"
image-studio install-skills --agent both | Out-Null
image-studio doctor
$exe = (Get-Command image-studio).Source
Write-Host "`nNext: register the MCP server with your agent:"
Write-Host "  claude mcp add image-studio --scope project -- `"$exe`" serve"
Write-Host "  codex mcp add image-studio -- `"$exe`" serve"
