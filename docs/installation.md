# Installation

## Requirements

- Python 3.10+ (tested with 3.13)
- Optional: **GIMP 3.x** for native filters, clone/heal tools and `.xcf` files
- Optional: a licensed **Photoshop** for `.psd` export

Everything else (Pillow, NumPy, OpenCV, the MCP SDK) installs from PyPI. No paid API or account is
needed.

## Install

```bash
git clone https://github.com/avishaydev/photoshop-skill.git
cd photoshop-skill
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
image-studio doctor
```

Or run the helper: `scripts/setup.sh` (macOS/Linux) / `scripts/setup.ps1` (Windows).

Optional extras: `pip install -e ".[rembg]"` (ML background removal; downloads a model on first use),
`".[psd]"` (psd-tools), `".[photoshop-windows]"` (pywin32 for Photoshop COM).

## GIMP 3

| Platform | How |
| --- | --- |
| Windows | Installer from https://www.gimp.org/downloads/ - auto-detected in `C:\Program Files\GIMP 3\bin` |
| macOS | DMG from gimp.org - auto-detected in `/Applications/GIMP.app` |
| Linux | Flatpak (`flathub org.gimp.GIMP`), the official AppImage, or a distro package with GIMP >= 3.0 |

Auto-detection looks for `gimp-console-3.x`, `gimp-console`, `gimp-3.x`, `gimp` on `PATH`. Otherwise set
`IMAGE_STUDIO_GIMP`:

```bash
export IMAGE_STUDIO_GIMP="/opt/GIMP-3.2.2-x86_64.AppImage"           # AppImage
export IMAGE_STUDIO_GIMP="flatpak run org.gimp.GIMP"                  # Flatpak (runs headless with -i)
```

AppImages need FUSE; in containers without FUSE extract it first
(`./GIMP-*.AppImage --appimage-extract`) and point `IMAGE_STUDIO_GIMP` at `squashfs-root/AppRun`.
Ubuntu 24.04's `apt install gimp` provides 2.10, which is detected but **not** supported.

Verify: `image-studio doctor --gimp-filters`.

## Configuration (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `IMAGE_STUDIO_WORKSPACE` | `<repo>/projects` | where projects are stored |
| `IMAGE_STUDIO_KNOWLEDGE_DIR` | `<repo>/knowledge` | knowledge base folder |
| `IMAGE_STUDIO_CACHE_DIR` | `<repo>/.image_studio_cache` | HTTP cache and temp files (git-ignored) |
| `IMAGE_STUDIO_ALLOWED_DIRS` | – | extra folders tools may READ (os.pathsep-separated). Workspace and the current directory are always readable |
| `IMAGE_STUDIO_OUTPUT_DIRS` | – | extra folders tools may WRITE. The workspace is always writable |
| `IMAGE_STUDIO_REFERENCE_DIRS` | – | folders searched by the `local` research provider |
| `IMAGE_STUDIO_REQUIRE_PLAN` | `1` | enforce the 10-step plan gate in the MCP server |
| `IMAGE_STUDIO_BACKEND` | `auto` | preferred backend for filters/clone/heal (`pillow`, `gimp`) |
| `IMAGE_STUDIO_GIMP` | auto-detect | GIMP command |
| `IMAGE_STUDIO_GIMP_TIMEOUT` | `180` | seconds per GIMP job |
| `IMAGE_STUDIO_MAX_PIXELS` | `120000000` | decompression-bomb and canvas limit |
| `IMAGE_STUDIO_MAX_REVISIONS` | `100` | undo revisions kept (checkpointed revisions are always kept) |
| `IMAGE_STUDIO_OPENVERSE_TOKEN` | – | optional Openverse OAuth token for higher rate limits |

## Platform notes

- **Windows**: use PowerShell; paths in env vars can use `;` separators. Photoshop automation needs
  `pywin32`.
- **macOS**: the first Photoshop automation prompts for Automation permission.
- **Linux/headless**: everything works headless; GIMP runs with `-i` (no display needed).
