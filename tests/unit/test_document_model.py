import json

import numpy as np
import pytest

from image_studio.core.project import Project
from image_studio.errors import NotFoundError, ValidationError


def test_create_project_writes_manifest(editor, settings):
    r = editor.create_project("My Poster", 300, 200, background="#ff0000")
    assert r["ok"] and r["document"]["width"] == 300
    root = settings.workspace / "my-poster"
    data = json.loads((root / "project.json").read_text())
    assert data["document"]["id"] == r["document_id"]
    assert (root / "revisions" / "1.json").exists()
    layers = editor.list_layers(r["document_id"])["layers"]
    assert [lay["name"] for lay in layers] == ["Background"]


def test_reload_from_disk(editor, doc, settings):
    from image_studio.editor import Editor
    editor.create_layer(doc, "Paint", fill_color="#00ff00")
    fresh = Editor()  # new process-equivalent: no in-memory cache
    names = [lay["name"] for lay in fresh.list_layers(doc)["layers"]]
    assert names == ["Paint", "Background"]


def test_stable_ids_and_order(editor, doc):
    a = editor.create_layer(doc, "A")["layer_id"]
    b = editor.create_layer(doc, "B")["layer_id"]
    c = editor.create_layer(doc, "C", above=a)["layer_id"]
    order = [lay["id"] for lay in editor.list_layers(doc)["layers"]]
    assert order[:3] == [b, c, a]
    editor.move_layer(doc, b, "bottom")
    assert editor.list_layers(doc)["layers"][-1]["id"] == b
    editor.move_layer(doc, b, "above", reference_layer_id=c)
    assert [lay["id"] for lay in editor.list_layers(doc)["layers"]][:2] == [b, c]
    editor.rename_layer(doc, a, "Alpha")
    assert editor.get_layer_info(doc, a)["layer"]["name"] == "Alpha"


def test_groups(editor, doc):
    a = editor.create_layer(doc, "A", fill_color="#ff0000")["layer_id"]
    b = editor.create_layer(doc, "B")["layer_id"]
    g = editor.create_group(doc, "Subject", [a, b])["group_id"]
    layers = editor.list_layers(doc)["layers"]
    assert layers[0]["id"] == g and layers[0]["children"] == [a, b]
    assert {lay["id"]: lay["depth"] for lay in layers}[a] == 1
    dup = editor.duplicate_layer(doc, g)["layer_id"]
    assert len(editor.get_layer_info(doc, dup)["layer"]["children"]) == 2
    editor.delete_layer(doc, g)
    ids = [lay["id"] for lay in editor.list_layers(doc)["layers"]]
    assert a not in ids and g not in ids and dup in ids


def test_invalid_layer_id_error(editor, doc):
    with pytest.raises(NotFoundError) as exc:
        editor.get_layer_info(doc, "lyr_nope")
    assert "list_layers" in exc.value.hint


def test_invalid_document_id(editor):
    with pytest.raises(NotFoundError):
        editor.list_layers("doc_missing")


def test_invalid_parameters(editor, doc):
    with pytest.raises(ValidationError):
        editor.set_layer_opacity(doc, editor.list_layers(doc)["layers"][0]["id"], 1.5)
    with pytest.raises(ValidationError):
        editor.set_blend_mode(doc, editor.list_layers(doc)["layers"][0]["id"], "sparkle")
    with pytest.raises(ValidationError):
        editor.create_project("x", 0, 10)


def test_open_document_protects_original(editor, photo, settings):
    r = editor.open_document(str(photo))
    d = r["document_id"]
    orig = editor.list_layers(d)["layers"][0]
    assert orig["locked_pixels"] and orig["name"] == "Original"
    with pytest.raises(ValidationError, match="locked"):
        editor.apply_filter(d, orig["id"], "gaussian_blur", {"radius": 2})
    proj = editor.project(d)
    assets = list(proj.doc.assets.values())
    assert assets and (proj.root / assets[0].path).read_bytes() == photo.read_bytes()


def test_path_security(editor, tmp_path):
    from image_studio.errors import PathSecurityError
    with pytest.raises(PathSecurityError):
        editor.open_document("/etc/hostname")


def test_layer_pixels_lazy_blobs(editor, doc):
    proj = editor.project(doc)
    layer = proj.doc.layers[proj.doc.root[0]]
    assert isinstance(layer.pixels, str)  # a blob reference, not an array
    arr = proj.blobs.get(layer.pixels)
    assert arr.shape == (120, 200, 4) and arr.dtype == np.uint8


def test_project_load_roundtrip(editor, doc):
    proj = editor.project(doc)
    again = Project.load(proj.root)
    assert again.doc.model_dump() == proj.doc.model_dump()
