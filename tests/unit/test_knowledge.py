import pytest

from image_studio.errors import ValidationError
from image_studio.knowledge.retrieval import search_knowledge
from image_studio.knowledge.storage import KnowledgeStore
from image_studio.knowledge.validation import validate_entry


def test_create_search_and_persist(settings):
    store = KnowledgeStore()
    r = store.upsert("subjects/animals/tiger", title="Tiger", tags=["tiger", "big cat", "stripes"],
                     sections={"Visual observations": "- Stripes are roughly vertical on the flanks.",
                               "Failure modes": "- Stripe pattern mirrored on both sides looks fake."},
                     sources=[{"url": "https://commons.wikimedia.org/wiki/File:X.jpg", "license": "CC0"}])
    assert r["created"]
    store.upsert("environments/forest", title="Forest", tags=["forest", "trees"],
                 sections={"Visual observations": "- Light shafts appear when air holds haze."})
    # a fresh store instance (= a later, independent task) finds it
    again = KnowledgeStore()
    res = search_knowledge("tiger stripe pattern", store=again)
    assert res["results"][0]["path"] == "subjects/animals/tiger"
    entry = again.read("subjects/animals/tiger")
    assert "mirrored" in entry.sections()["Failure modes"]


def test_append_merges_and_dedupes(settings):
    store = KnowledgeStore()
    store.upsert("techniques/clone-stamp", title="Clone stamp", tags=["retouch"],
                 sections={"Editing recipe": "- Sample from varied sources."})
    store.upsert("techniques/clone-stamp", tags=["retouch", "clone"],
                 sections={"Editing recipe": "- Sample from varied sources.\n- Lower opacity for skin."})
    e = store.read("techniques/clone-stamp")
    assert e.tags == ["retouch", "clone"]
    assert e.body.count("Sample from varied sources") >= 1


def test_validation_rules(settings):
    store = KnowledgeStore()
    with pytest.raises(ValidationError):
        store.upsert("x/high", title="X", confidence="high", sections={"Notes": "claim"})  # no sources
    with pytest.raises(ValidationError):
        store.upsert("x/img", title="X", sections={"Notes": "data:image/png;base64,AAAA"})
    with pytest.raises(ValidationError):
        store.upsert("../escape", title="X", sections={"Notes": "a"})


def test_repository_knowledge_base_is_valid():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "knowledge"
    store = KnowledgeStore(root)
    entries = store.all()
    assert len(entries) >= 13
    for e in entries:
        errors = [p for p in validate_entry(e) if p["level"] == "error"]
        assert not errors, (e.path, errors)
    hits = search_knowledge("peacock feathers iridescence ocean reflection", store=store)["results"]
    assert {h["path"] for h in hits[:4]} & {"subjects/birds/peacock", "materials/feathers"}
