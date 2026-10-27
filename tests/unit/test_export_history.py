import json
import zipfile

import numpy as np
import pytest
from PIL import Image

from image_studio.errors import PathSecurityError, StudioError, ValidationError


@pytest.mark.parametrize("fmt,pil", [("png", "PNG"), ("jpeg", "JPEG"), ("webp", "WEBP"), ("tiff", "TIFF")])
def test_export_formats(editor, doc, fmt, pil):
    r = editor.export_image(doc, format=fmt)
    assert r["verification"]["matches"]
    with Image.open(r["export_path"]) as im:
        assert im.format == pil and im.size == (200, 120)
    assert json.loads(open(r["credits_path"]).read())["document"] == "Test"


def test_export_resize_and_path_rules(editor, doc):
    r = editor.export_image(doc, path="exports/small.png", width=100)
    assert r["size"] == [100, 60]
    with pytest.raises(PathSecurityError):
        editor.export_image(doc, path="/tmp/../etc/evil.png")


def test_preview(editor, doc):
    r = editor.render_preview(doc, max_size=100)
    with Image.open(r["preview_path"]) as im:
        assert max(im.size) == 100
    lid = editor.list_layers(doc)["layers"][0]["id"]
    assert editor.render_preview(doc, layer_id=lid, region=[0, 0, 50, 50])["preview_size"] == [50, 50]


def test_ora_roundtrip(editor, doc):
    lid = editor.create_shape_layer(doc, "ellipse", 20, 20, 60, 40, fill="#ff0000")["layer_id"]
    editor.set_layer_properties(doc, lid, blend_mode="multiply", opacity=0.7)
    editor.create_group(doc, "Group", [lid])
    r = editor.save_document(doc, "ora")
    with zipfile.ZipFile(r["native_file"]) as z:
        assert z.read("mimetype") == b"image/openraster"
        assert z.infolist()[0].filename == "mimetype"
        xml = z.read("stack.xml").decode()
        assert "svg:multiply" in xml and "<stack" in xml
    before = editor.render_doc(editor.project(doc))
    d2 = editor.open_document(r["native_file"], name="reopened")["document_id"]
    after = editor.render_doc(editor.project(d2))
    assert np.abs(before - after).max() < 2 / 255


def test_unavailable_native_format_reports_clearly(editor, doc):
    from image_studio.errors import UnsupportedOperationError
    with pytest.raises(UnsupportedOperationError) as exc:
        editor.save_document(doc, "psd")
    assert "photoshop" in exc.value.message.lower()


def test_checkpoint_undo_restore(editor, doc):
    editor.create_checkpoint(doc, "start")
    lid = editor.create_layer(doc, "a", fill_color="#ff0000")["layer_id"]
    editor.create_layer(doc, "b")
    assert len(editor.list_layers(doc)["layers"]) == 3
    editor.undo(doc)
    assert len(editor.list_layers(doc)["layers"]) == 2
    editor.restore_checkpoint(doc, "start")
    ids = [x["id"] for x in editor.list_layers(doc)["layers"]]
    assert lid not in ids and len(ids) == 1
    editor.undo(doc)  # undoing the restore brings layer 'a' back
    assert lid in [x["id"] for x in editor.list_layers(doc)["layers"]]
    hist = editor.get_history(doc)["history"]
    assert [h["op"] for h in hist][-2:] == ["restore_checkpoint", "undo"]


def test_failed_operation_leaves_project_consistent(editor, doc):
    proj = editor.project(doc)
    rev = proj.doc.revision
    snapshot = proj.doc.model_dump()
    lid = proj.doc.root[0]
    with pytest.raises(ValidationError):
        editor.edit_layer_mask(doc, lid, "paint")  # no mask -> fails inside transaction
    assert proj.doc.revision == rev and proj.doc.model_dump() == snapshot
    on_disk = json.loads((proj.root / "project.json").read_text())
    assert on_disk["document"]["revision"] == rev


def test_garbage_collect(editor, doc):
    lid = editor.create_layer(doc, "x", fill_color="#123456")["layer_id"]
    editor.delete_layer(doc, lid)
    proj = editor.project(doc)
    res = proj.garbage_collect()
    assert res["kept_blobs"] >= 1


def test_corrupt_blob_reported(editor, doc):
    proj = editor.project(doc)
    blob = proj.doc.layers[proj.doc.root[0]].pixels
    proj.blobs.path(blob).unlink()
    proj.blobs._cache.clear()
    with pytest.raises(StudioError):
        editor.export_image(doc)
