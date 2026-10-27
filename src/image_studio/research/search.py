"""Research service: multi-provider search, reference download with provenance, observation notes."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from ..core.ids import new_id
from ..core.project import Project
from ..errors import NotFoundError, ResearchError, ValidationError
from ..security import safe_child
from .http import PoliteClient
from .licensing import assess_reuse, attribution_line
from .models import ReferenceCandidate
from .providers import LocalFolderProvider, OpenverseProvider, ReferenceProvider, WikimediaCommonsProvider


class ResearchService:
    def __init__(self, providers: dict[str, ReferenceProvider] | None = None):
        if providers is None:
            client = PoliteClient()
            providers = {"wikimedia_commons": WikimediaCommonsProvider(client), "openverse": OpenverseProvider(),
                         "local": LocalFolderProvider()}
        self.providers = providers

    def provider(self, name: str) -> ReferenceProvider:
        if name not in self.providers:
            raise ValidationError(f"Unknown provider '{name}'", details={"available": list(self.providers)})
        return self.providers[name]

    def list_providers(self) -> list[dict[str, Any]]:
        return [p.status() for p in self.providers.values()]

    def search(self, query: str, providers: list[str] | None = None, limit: int = 8,
               reusable_only: bool = False, commercial: bool = False) -> dict[str, Any]:
        names = providers or [n for n, p in self.providers.items() if p.status().get("available")]
        results: list[dict[str, Any]] = []
        errors: dict[str, str] = {}
        for name in names:
            try:
                hits = self.provider(name).search(query, limit=limit, commercial=commercial)
            except Exception as exc:  # one failing provider must not hide the others
                errors[name] = str(exc)
                continue
            for c in hits:
                c.reuse = assess_reuse(c.license)
                if reusable_only and not c.reuse["composite_allowed"]:
                    continue
                if commercial and not c.reuse["commercial_allowed"]:
                    continue
                results.append(c.model_dump(mode="json") | {"reference_key": c.key})
        out: dict[str, Any] = {"ok": not (errors and not results), "query": query, "count": len(results),
                               "results": results,
                               "note": "Search hits are candidates only. Fetch thumbnails and LOOK at them; "
                                       "snippets and titles are not enough to learn visual details."}
        if errors:
            out["provider_errors"] = errors
        return out

    # ----- download -------------------------------------------------------------------------
    def fetch_reference(self, project: Project, reference_key: str, size: str = "thumbnail",
                        purpose: str = "study") -> dict[str, Any]:
        """Download a reference into the project's references/ folder with a provenance record.

        size: thumbnail (default; enough to study) | large (~2048 px provider rendition; preferred for
        compositing) | full (original file; may be very large or throttled by the provider).
        purpose: study | composite.
        """
        if ":" not in reference_key:
            raise ValidationError("reference_key must look like 'provider:id' (from search results)")
        if size not in ("thumbnail", "large", "full"):
            raise ValidationError("size must be thumbnail, large or full")
        pname, pid = reference_key.split(":", 1)
        cand = self.provider(pname).get(pid, thumb_width=2048 if size == "large" else None)
        cand.reuse = assess_reuse(cand.license)
        if purpose == "composite" and not cand.reuse["composite_allowed"]:
            raise ValidationError(f"License does not allow compositing: {cand.reuse['notes']}",
                                  details={"license": cand.license.model_dump() if cand.license else None})
        if pname == "local":
            data = Path(pid).read_bytes()
        else:
            if size != "thumbnail" and purpose != "composite":
                raise ValidationError("Download large/full images only for compositing (purpose='composite'); "
                                      "thumbnails are sufficient for study")
            if size == "large" and pname == "wikimedia_commons":
                url = cand.thumbnail_url or cand.image_url
            else:
                url = cand.thumbnail_url if size == "thumbnail" else cand.image_url
            if not url:
                raise ResearchError("Provider gave no image URL for this result")
            data, _ = PoliteClient(min_interval=0.5).get_bytes(url)
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                fmt = (im.format or "PNG").upper()
                w, h = im.size
                if fmt not in ("JPEG", "PNG", "WEBP", "TIFF", "GIF", "BMP"):
                    raise ResearchError(f"Unsupported reference format {fmt}")
                ref_id = new_id("ref")
                ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif", "GIF": ".gif",
                       "BMP": ".bmp"}[fmt]
                if size == "thumbnail" and max(w, h) > 1024:
                    im = im.convert("RGB") if im.mode not in ("RGB", "RGBA") else im
                    im.thumbnail((1024, 1024))
                    w, h = im.size
                    ext = ".png"
                    local = safe_child(project.root / "references", f"{ref_id}{ext}")
                    im.save(local, "PNG")
                else:  # keep the original encoding byte-for-byte (no re-compression, no bloat)
                    local = safe_child(project.root / "references", f"{ref_id}{ext}")
                    local.write_bytes(data)
        except ResearchError:
            raise
        except Exception as exc:
            raise ResearchError(f"Downloaded file is not a valid image: {exc}") from exc
        rec = {"id": ref_id, "reference_key": reference_key, "provider": pname, "provider_id": pid,
               "title": cand.title, "source_page": cand.source_page, "image_url": cand.image_url,
               "local_path": f"references/{local.name}", "size": [w, h], "download": size, "purpose": purpose,
               "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
               "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "license": cand.license.model_dump() if cand.license else None, "reuse": cand.reuse,
               "attribution": attribution_line(cand.license, cand.title), "description": cand.description,
               "role": "reference_only" if purpose == "study" else "composite_candidate"}
        (project.root / "references" / f"{ref_id}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False),
                                                                     encoding="utf-8")
        return {"ok": True, "reference_id": ref_id, "local_path": str(local), **{k: rec[k] for k in (
            "title", "source_page", "license", "reuse", "attribution", "size", "role")},
                "hint": "View the image file to study it, then record_observation with what you learned."}

    # ----- notes ------------------------------------------------------------------------------------
    @staticmethod
    def _notes_path(project: Project) -> Path:
        return project.root / "research" / "notes.json"

    def load_notes(self, project: Project) -> dict[str, Any]:
        p = self._notes_path(project)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"observations": [], "summary": None}

    def record_observation(self, project: Project, aspect: str, observation: str, reference_ids: list[str],
                           confidence: str = "medium", subject: str | None = None) -> dict[str, Any]:
        if confidence not in ("low", "medium", "high"):
            raise ValidationError("confidence must be low, medium or high")
        if not observation.strip():
            raise ValidationError("observation must not be empty")
        known = {p.stem for p in (project.root / "references").glob("*.json")}
        missing = [r for r in reference_ids if r not in known]
        if missing:
            raise NotFoundError(f"Unknown reference ids: {missing}",
                                hint="Observations must cite fetched references (or pass [] and confidence='low' "
                                     "for general knowledge, which will be marked unsupported).")
        notes = self.load_notes(project)
        obs = {"id": new_id("obs"), "subject": subject, "aspect": aspect, "observation": observation.strip(),
               "reference_ids": reference_ids, "confidence": confidence if reference_ids else "low",
               "supported": bool(reference_ids),
               "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        notes["observations"].append(obs)
        self._notes_path(project).write_text(json.dumps(notes, indent=1, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "observation": obs, "total_observations": len(notes["observations"])}

    def research_summary(self, project: Project) -> dict[str, Any]:
        notes = self.load_notes(project)
        refs = []
        for p in sorted((project.root / "references").glob("*.json")):
            rec = json.loads(p.read_text(encoding="utf-8"))
            refs.append({k: rec.get(k) for k in ("id", "title", "provider", "source_page", "role", "attribution")}
                        | {"license": (rec.get("license") or {}).get("short_name")})
        by_aspect: dict[str, list[dict]] = {}
        for o in notes["observations"]:
            by_aspect.setdefault(o["aspect"], []).append(o)
        unsupported = [o for o in notes["observations"] if not o["supported"]]
        return {"ok": True, "references": refs, "observations_by_aspect": by_aspect,
                "unsupported_observations": len(unsupported),
                "note": "Only observations with reference_ids are supported by evidence."}


_service: ResearchService | None = None


def get_research_service() -> ResearchService:
    global _service
    if _service is None:
        _service = ResearchService()
    return _service


def set_research_service(svc: ResearchService | None) -> None:
    global _service
    _service = svc


__all__ = ["ResearchService", "ReferenceCandidate", "get_research_service", "set_research_service"]
