import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from image_studio.core.provenance import LicenseInfo
from image_studio.errors import ValidationError
from image_studio.research.licensing import assess_reuse, normalize
from image_studio.research.providers import OpenverseProvider, WikimediaCommonsProvider
from image_studio.research.search import ResearchService

FIX = Path(__file__).resolve().parents[1] / "fixtures"


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, params=None, headers=None, use_cache=True):
        self.calls.append((url, params))
        return self.payload


@pytest.mark.parametrize("short,url,code", [
    ("CC BY-SA 4.0", None, "cc-by-sa"), ("CC0", None, "cc0"), ("Public domain", None, "public-domain"),
    ("CC BY-NC-ND 2.0", None, "cc-by-nc-nd"), (None, "https://creativecommons.org/licenses/by/3.0/", "cc-by"),
    ("All rights reserved", None, "all rights reserved"),
])
def test_normalize(short, url, code):
    assert normalize(short, url) == code


def test_assess_reuse():
    assert assess_reuse(None)["composite_allowed"] is False
    assert assess_reuse(LicenseInfo(short_name="CC0"))["attribution_required"] is False
    nd = assess_reuse(LicenseInfo(short_name="CC BY-ND 4.0"))
    assert nd["composite_allowed"] is False and "NoDerivatives" in nd["notes"]
    sa = assess_reuse(LicenseInfo(short_name="CC BY-SA 4.0"))
    assert sa["composite_allowed"] and sa["share_alike"] and sa["attribution_required"]
    assert assess_reuse(LicenseInfo(short_name="Mystery license"))["composite_allowed"] is False


def test_wikimedia_parsing():
    payload = json.loads((FIX / "wikimedia_search_tiger.json").read_text())
    client = FakeClient(payload)
    hits = WikimediaCommonsProvider(client).search("tiger", limit=2)
    assert len(hits) == 2
    h = hits[0]
    assert h.provider_id == "3625607" and h.license.short_name == "Public domain"
    assert h.license.author == "Dave Pape" and "<" not in (h.description or "")
    assert h.license.attribution_required is False
    assert hits[1].license.url.startswith("https://creativecommons.org/licenses/by-sa")
    url, params = client.calls[0]
    assert params["generator"] == "search" and "filetype:bitmap" in params["gsrsearch"]
    assert "extmetadata" in params["iiprop"]


def test_openverse_parsing():
    payload = json.loads((FIX / "openverse_search_tiger.json").read_text())
    hits = OpenverseProvider(FakeClient(payload)).search("tiger")
    assert hits[0].license.short_name == "CC0 1.0" and hits[0].license.attribution_required is False
    assert hits[1].license.short_name == "CC BY-ND 2.0"
    assert assess_reuse(hits[1].license)["composite_allowed"] is False


class FakeProvider:
    name = "fake"

    def __init__(self, cand):
        self.cand = cand

    def search(self, query, limit=10, **kw):
        return [self.cand]

    def get(self, pid, thumb_width=None):
        return self.cand

    def status(self):
        return {"name": "fake", "available": True}


def _png_bytes():
    buf = io.BytesIO()
    Image.fromarray(np.full((40, 60, 3), 120, np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def test_fetch_reference_records_provenance(editor, doc, monkeypatch):
    from image_studio.research import search as search_mod
    from image_studio.research.models import ReferenceCandidate
    cand = ReferenceCandidate(provider="fake", provider_id="1", title="Tiger", source_page="https://example.org/t",
                              image_url="https://example.org/t.jpg", thumbnail_url="https://example.org/t_s.jpg",
                              license=LicenseInfo(short_name="CC BY 4.0", author="A. Author",
                                                  source_page="https://example.org/t"))
    svc = ResearchService({"fake": FakeProvider(cand)})
    monkeypatch.setattr(search_mod.PoliteClient, "get_bytes", lambda self, url, max_bytes=0: (_png_bytes(), "image/png"))
    res = svc.search("tiger")
    assert res["results"][0]["reuse"]["composite_allowed"]
    proj = editor.project(doc)
    f = svc.fetch_reference(proj, "fake:1")
    assert f["role"] == "reference_only" and Path(f["local_path"]).exists()
    rec = json.loads((proj.root / "references" / f"{f['reference_id']}.json").read_text())
    assert rec["license"]["author"] == "A. Author" and rec["sha256"]
    with pytest.raises(ValidationError):
        svc.fetch_reference(proj, "fake:1", size="full", purpose="study")
    obs = svc.record_observation(proj, "stripes", "Stripes are vertical on the flank", [f["reference_id"]], "high")
    assert obs["observation"]["supported"]
    obs2 = svc.record_observation(proj, "fur", "General knowledge claim", [], "high")
    assert obs2["observation"]["confidence"] == "low" and not obs2["observation"]["supported"]
    summary = svc.research_summary(proj)
    assert summary["unsupported_observations"] == 1 and "stripes" in summary["observations_by_aspect"]
    # composite import keeps license + attribution warning
    r = editor.import_image_as_layer(doc, reference_id=f["reference_id"])
    assert any("Attribution required" in w for w in r["warnings"])
    exp = editor.export_image(doc)
    assert exp["attribution_required"] and "A. Author" in exp["credits"][0]
    from image_studio.research.reference_analysis import analyze_references
    ana = analyze_references(proj, [f["reference_id"]])
    assert Path(ana["contact_sheet"]).exists() and ana["references"][0]["palette"]


def test_nd_reference_cannot_be_composited(editor, doc, monkeypatch):
    from image_studio.research import search as search_mod
    from image_studio.research.models import ReferenceCandidate
    cand = ReferenceCandidate(provider="fake", provider_id="2", title="ND", thumbnail_url="https://e.org/x.jpg",
                              license=LicenseInfo(short_name="CC BY-ND 4.0"))
    svc = ResearchService({"fake": FakeProvider(cand)})
    monkeypatch.setattr(search_mod.PoliteClient, "get_bytes", lambda self, url, max_bytes=0: (_png_bytes(), "image/png"))
    f = svc.fetch_reference(editor.project(doc), "fake:2")
    with pytest.raises(ValidationError, match="may not be composited"):
        editor.import_image_as_layer(doc, reference_id=f["reference_id"])
    with pytest.raises(ValidationError):
        svc.fetch_reference(editor.project(doc), "fake:2", size="full", purpose="composite")


def test_provider_failure_is_isolated():
    class Broken(FakeProvider):
        def search(self, *a, **k):
            raise RuntimeError("down")
    from image_studio.research.models import ReferenceCandidate
    ok = FakeProvider(ReferenceCandidate(provider="fake", provider_id="1", title="t"))
    svc = ResearchService({"broken": Broken(None), "fake": ok})
    res = svc.search("x")
    assert res["count"] == 1 and "broken" in res["provider_errors"]


def test_http_refuses_non_https():
    from image_studio.errors import ResearchError
    from image_studio.research.http import PoliteClient
    with pytest.raises(ResearchError):
        PoliteClient().get_bytes("http://example.org/a.jpg")


def test_tampered_reference_record_cannot_escape_project(editor, doc):
    from image_studio.errors import PathSecurityError
    proj = editor.project(doc)
    (proj.root / "references" / "ref_evil.json").write_text(json.dumps(
        {"id": "ref_evil", "local_path": "../../../../etc/hostname", "license": {"short_name": "CC0"}}))
    with pytest.raises(PathSecurityError):
        editor.import_image_as_layer(doc, reference_id="ref_evil")
