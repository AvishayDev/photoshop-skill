"""License interpretation for reference images.

This is a conservative helper, not legal advice. It classifies common
Creative Commons / public-domain markers so the agent knows whether an image
may be *composited into* a deliverable (and with what attribution), versus
only studied as a visual reference. Unknown licenses are never treated as
reusable.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.provenance import LicenseInfo


def normalize(short_name: str | None, url: str | None = None) -> str:
    s = (short_name or "").strip().lower()
    u = (url or "").lower()
    if not s and u:
        s = u
    s = s.replace("_", " ").replace("-", " ")
    if "publicdomain/zero" in u or s in ("cc0", "cc0 1.0", "cc zero") or "cc0" in s:
        return "cc0"
    if "public domain" in s or s in ("pd", "pdm", "pdm 1.0") or "publicdomain/mark" in u or s.startswith("pd "):
        return "public-domain"
    m = re.search(r"\bcc\s*by(?:\s*(nc))?(?:\s*(sa|nd))?(?:\s*(nd|sa))?", s)
    if not m and "creativecommons.org/licenses/" in u:
        m2 = re.search(r"licenses/([a-z\-]+)/", u)
        if m2:
            return "cc-" + m2.group(1)
    if m:
        parts = ["cc", "by"] + [p for p in m.groups() if p]
        return "-".join(parts)
    if "gfdl" in s or "gnu free documentation" in s:
        return "gfdl"
    if not s:
        return "unknown"
    return s


def assess_reuse(lic: LicenseInfo | None) -> dict[str, Any]:
    """Return {'code', 'composite_allowed', 'commercial_allowed', 'attribution_required', 'share_alike', 'notes'}."""
    if lic is None:
        return {"code": "unknown", "composite_allowed": False, "commercial_allowed": False,
                "attribution_required": None, "share_alike": False,
                "notes": "No license information: use only as a visual reference, not as an asset."}
    code = normalize(lic.short_name, lic.url)
    out = {"code": code, "composite_allowed": False, "commercial_allowed": False,
           "attribution_required": True, "share_alike": False, "notes": ""}
    if code in ("cc0", "public-domain"):
        out.update(composite_allowed=True, commercial_allowed=True, attribution_required=False,
                   notes="Public domain / CC0. Crediting the source is still good practice.")
    elif code.startswith("cc-by"):
        nc, nd, sa = "-nc" in code, "-nd" in code, "-sa" in code
        out.update(composite_allowed=not nd, commercial_allowed=not nc, share_alike=sa)
        notes = ["Attribution required (author, source, license link)."]
        if nd:
            notes.append("NoDerivatives: may not be modified or composited; reference only.")
        if nc:
            notes.append("NonCommercial: not for commercial deliverables.")
        if sa:
            notes.append("ShareAlike: derivative images must be released under the same license.")
        out["notes"] = " ".join(notes)
    elif code == "gfdl":
        out.update(composite_allowed=True, commercial_allowed=True, share_alike=True,
                   notes="GFDL: copyleft with burdensome notice requirements; prefer other sources.")
    else:
        out["notes"] = f"License '{lic.short_name}' is not recognized; treat as reference only unless verified."
    if lic.attribution_required is False and code not in ("cc0", "public-domain"):
        out["notes"] += " Source states attribution is not required."
    return out


def attribution_line(lic: LicenseInfo | None, title: str | None = None) -> str | None:
    if lic is None:
        return None
    parts = []
    if title:
        parts.append(f'"{title}"')
    if lic.author:
        parts.append(f"by {lic.author}")
    if lic.source_page:
        parts.append(f"({lic.source_page})")
    if lic.short_name:
        parts.append(f"licensed {lic.short_name}" + (f" <{lic.url}>" if lic.url else ""))
    return " ".join(parts) if parts else None
