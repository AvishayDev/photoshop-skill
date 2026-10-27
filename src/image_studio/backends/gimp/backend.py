"""GIMP 3.x native backend.

Integration choice: GIMP's documented batch mode with the Python 3
``python-fu-eval`` batch interpreter (GIMP >= 3.0)::

    gimp-console -i --batch-interpreter=python-fu-eval -b - --quit

Each call starts a headless GIMP process (no GUI, no network socket), feeds it
a tiny bootstrap on stdin that runs ``bridge/gimp_bridge.py`` against a JSON
job file, and reads ``result.json`` back. Communication is limited to files in
a private temporary directory, so no local port is exposed. The job file can
only name operations from the bridge's fixed allow-list.

Trade-off: a GIMP start costs ~2-4 s, so GIMP is used for operations where its
native implementation matters (GEGL filters, XCF read/write, native clone and
heal tools), while layer bookkeeping and compositing stay in the core engine.
GIMP 2.10 is detected but not supported (its Python-Fu is Python 2 only).
"""

from __future__ import annotations

import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ...config import get_settings
from ...errors import (
    BackendExecutionError,
    BackendUnavailableError,
    UnsupportedOperationError,
    ValidationError,
)
from ..base import (
    CAP_CLONE,
    CAP_EXPORT_NATIVE,
    CAP_FILTER,
    CAP_HEAL,
    CAP_IMPORT_NATIVE,
    Backend,
    BackendStatus,
    ImportedDocument,
    ImportedLayer,
)

BRIDGE = Path(__file__).parent / "bridge" / "gimp_bridge.py"
_CANDIDATES = ["gimp-console-3.2", "gimp-console-3.0", "gimp-console-3", "gimp-console", "gimp-3.2", "gimp-3.0",
               "gimp-3", "gimp"]
_PLATFORM_PATHS = [
    "/Applications/GIMP.app/Contents/MacOS/gimp-console",
    "/Applications/GIMP.app/Contents/MacOS/gimp",
    r"C:\Program Files\GIMP 3\bin\gimp-console-3.2.exe",
    r"C:\Program Files\GIMP 3\bin\gimp-console-3.0.exe",
    r"C:\Program Files\GIMP 3\bin\gimp-console.exe",
]
_GEGL_NAME = re.compile(r"^gegl:[a-z0-9][a-z0-9-]*$")
_PARAM_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def find_gimp() -> list[str] | None:
    """Return the GIMP command (as argv list) or None."""
    configured = get_settings().gimp_executable
    if configured:
        argv = shlex.split(configured, posix=os.name != "nt")
        return argv if argv and (shutil.which(argv[0]) or Path(argv[0]).exists()) else None
    for name in _CANDIDATES:
        p = shutil.which(name)
        if p:
            return [p]
    for p in _PLATFORM_PATHS:
        if Path(p).exists():
            return [p]
    return None


@functools.lru_cache(maxsize=8)
def _probe_version(cmd: tuple[str, ...]) -> str | None:
    try:
        out = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"version\s+(\d+\.\d+(?:\.\d+)?)", out.stdout + out.stderr)
    return m.group(1) if m else None


class GimpBackend(Backend):
    name = "gimp"

    def __init__(self):
        self._probe: dict[str, Any] | None = None

    # ----- discovery -----------------------------------------------------------
    def command(self) -> list[str] | None:
        return find_gimp()

    def status(self) -> BackendStatus:
        cmd = self.command()
        how = ("Install GIMP 3.x (https://www.gimp.org/downloads/) or set IMAGE_STUDIO_GIMP to the GIMP "
               "executable / AppImage / 'flatpak run org.gimp.GIMP'. Then run `image-studio doctor`.")
        if not cmd:
            return BackendStatus(self.name, False, detail="GIMP executable not found", missing=["gimp>=3.0"],
                                 how_to_enable=how)
        version = _probe_version(tuple(cmd))
        if not version:
            return BackendStatus(self.name, False, detail=f"Could not run {' '.join(cmd)} --version",
                                 how_to_enable=how)
        major = int(version.split(".")[0])
        if major < 3:
            return BackendStatus(self.name, False, version=version,
                                 detail="GIMP 2.x found; native integration requires GIMP 3.x (Python 3 plug-in API)",
                                 missing=["gimp>=3.0"], how_to_enable=how)
        return BackendStatus(self.name, True, version=version, native_formats=["xcf", "psd (import)", "ora"],
                             detail=f"Using {' '.join(cmd)}")

    def capabilities(self) -> set[str]:
        return {CAP_FILTER, CAP_CLONE, CAP_HEAL, CAP_EXPORT_NATIVE, CAP_IMPORT_NATIVE}

    def _require(self) -> list[str]:
        st = self.status()
        if not st.available:
            raise BackendUnavailableError(f"GIMP backend unavailable: {st.detail}", hint=st.how_to_enable)
        return self.command()  # type: ignore[return-value]

    # ----- execution -----------------------------------------------------------
    def run_job(self, ops: list[dict[str, Any]], work_dir: Path | None = None) -> list[dict[str, Any]]:
        cmd = self._require()
        own_dir = work_dir is None
        tmp = Path(tempfile.mkdtemp(prefix="gimpjob_", dir=_tmp_root())) if own_dir else work_dir
        try:
            job = tmp / "job.json"
            job.write_text(json.dumps({"ops": ops}), encoding="utf-8")
            bootstrap = (
                "import os\n"
                f"os.environ['IMAGE_STUDIO_JOB'] = {str(job)!r}\n"
                f"exec(compile(open({str(BRIDGE)!r}, encoding='utf-8').read(), {str(BRIDGE)!r}, 'exec'))\n"
            )
            env = os.environ.copy()
            try:
                proc = subprocess.run([*cmd, "-i", "--no-splash", "--batch-interpreter=python-fu-eval", "-b", "-",
                                       "--quit"], input=bootstrap, capture_output=True, text=True,
                                      timeout=get_settings().gimp_timeout, env=env, cwd=str(tmp))
            except subprocess.TimeoutExpired as exc:
                raise BackendExecutionError("GIMP did not finish in time",
                                            hint="Increase IMAGE_STUDIO_GIMP_TIMEOUT or simplify the job") from exc
            result_file = tmp / "result.json"
            if not result_file.exists():
                tail = "\n".join((proc.stderr or "").splitlines()[-15:])
                raise BackendExecutionError("GIMP exited without producing a result",
                                            details={"returncode": proc.returncode, "stderr_tail": tail})
            results = json.loads(result_file.read_text(encoding="utf-8"))["results"]
            for r in results:
                if not r.get("ok"):
                    raise BackendExecutionError(f"GIMP operation '{r['op']}' failed: {r.get('error')}",
                                                details={"traceback": r.get("traceback")})
            return [r["result"] for r in results]
        finally:
            if own_dir:
                shutil.rmtree(tmp, ignore_errors=True)

    def probe(self) -> dict[str, Any]:
        if self._probe is None:
            self._probe = self.run_job([{"op": "probe"}])[0]
        return self._probe

    def filters(self) -> list[str]:
        try:
            return self.probe()["gegl_operations"]
        except Exception:
            return []

    def filter_info(self, operation: str) -> dict[str, Any]:
        self._check_gegl(operation)
        return self.run_job([{"op": "filter_info", "args": {"operation": operation}}])[0]

    def _check_gegl(self, operation: str) -> None:
        if not _GEGL_NAME.match(operation):
            raise ValidationError("GIMP filters are GEGL operation names such as 'gegl:gaussian-blur'")
        avail = self.filters()
        if avail and operation not in avail:
            raise UnsupportedOperationError(f"GEGL operation '{operation}' is not available in this GIMP",
                                            details={"examples": avail[:40]})

    # ----- operations ------------------------------------------------------------
    def apply_filter(self, rgba: np.ndarray, name: str, params: dict[str, Any]) -> np.ndarray:
        self._check_gegl(name)
        for k, v in (params or {}).items():
            if not _PARAM_NAME.match(k) or not isinstance(v, (int, float, bool, str)):
                raise ValidationError(f"Invalid GEGL parameter {k!r}; values must be scalars")
        with tempfile.TemporaryDirectory(prefix="gimpf_", dir=_tmp_root()) as d:
            src, dst = Path(d) / "in.png", Path(d) / "out.png"
            Image.fromarray(rgba, "RGBA").save(src)
            self.run_job([{"op": "filter", "args": {"input": str(src), "output": str(dst), "operation": name,
                                                     "params": params or {}}}], Path(d))
            return _read_rgba(dst, rgba.shape)

    def clone_stamp(self, target, source, *, source_point, strokes, size=30, hardness=0.6, opacity=1.0,
                    aligned=True, spacing=0.12):
        with tempfile.TemporaryDirectory(prefix="gimpc_", dir=_tmp_root()) as d:
            t, s, o = Path(d) / "t.png", Path(d) / "s.png", Path(d) / "o.png"
            Image.fromarray(target, "RGBA").save(t)
            Image.fromarray(source, "RGBA").save(s)
            res = self.run_job([{"op": "clone", "args": {
                "target": str(t), "source": str(s), "output": str(o), "source_point": list(source_point),
                "strokes": strokes, "size": size, "hardness": hardness, "opacity": opacity, "aligned": aligned}}],
                Path(d))[0]
            return _read_rgba(o, target.shape), {"native_tool": "gimp-clone", **res}

    def heal(self, target, *, source_point, strokes, size=30, hardness=0.5, method="auto"):
        if source_point is None:
            raise UnsupportedOperationError("GIMP's heal tool needs a source point",
                                            hint="Use backend='pillow' for spot healing (inpainting)")
        with tempfile.TemporaryDirectory(prefix="gimph_", dir=_tmp_root()) as d:
            t, o = Path(d) / "t.png", Path(d) / "o.png"
            Image.fromarray(target, "RGBA").save(t)
            res = self.run_job([{"op": "heal", "args": {
                "target": str(t), "output": str(o), "source_point": list(source_point), "strokes": strokes,
                "size": size, "hardness": hardness}}], Path(d))[0]
            return _read_rgba(o, target.shape), {"native_tool": "gimp-heal", **res}

    def export_native(self, spec: dict[str, Any], out_path: Path, fmt: str) -> dict[str, Any]:
        if fmt != "xcf":
            raise UnsupportedOperationError(f"GIMP backend writes 'xcf' here, not '{fmt}'")
        self.run_job([{"op": "export_xcf", "args": {"document": spec, "output": str(out_path)}}])
        if not out_path.exists():
            raise BackendExecutionError("GIMP reported success but no XCF file was written")
        return {"format": "xcf", "path": str(out_path)}

    def import_native(self, path: Path, work_dir: Path) -> ImportedDocument:
        work_dir.mkdir(parents=True, exist_ok=True)
        res = self.run_job([{"op": "import", "args": {"input": str(path), "out_dir": str(work_dir)}}])[0]

        def conv(items):
            out = []
            for it in items:
                out.append(ImportedLayer(
                    name=it["name"], kind=it["kind"], x=int(it["x"]), y=int(it["y"]),
                    png=Path(it["png"]) if it.get("png") else None, visible=bool(it["visible"]),
                    opacity=float(it["opacity"]), blend_mode=it.get("blend_mode", "normal"),
                    mask_png=Path(it["mask_png"]) if it.get("mask_png") else None,
                    mask_enabled=bool(it.get("mask_enabled", True)), text=it.get("text"),
                    children=conv(it.get("children", []))))
            return out

        return ImportedDocument(width=res["width"], height=res["height"], layers=conv(res["layers"]),
                                resolution=float(res.get("resolution") or 72))


def _tmp_root() -> str | None:
    root = get_settings().cache_dir / "tmp"
    try:
        root.mkdir(parents=True, exist_ok=True)
        return str(root)
    except OSError:
        return None


def _read_rgba(path: Path, shape) -> np.ndarray:
    if not path.exists():
        raise BackendExecutionError("GIMP did not write the expected output image")
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGBA")).copy()
    if arr.shape[:2] != tuple(shape[:2]):
        raise BackendExecutionError(f"GIMP returned {arr.shape[:2]}, expected {tuple(shape[:2])}")
    return arr


if __name__ == "__main__":  # manual diagnostic: python -m image_studio.backends.gimp.backend
    b = GimpBackend()
    print(json.dumps(b.status().to_dict(), indent=2))
    if b.status().available:
        print(len(b.filters()), "GEGL operations")
    sys.exit(0)
