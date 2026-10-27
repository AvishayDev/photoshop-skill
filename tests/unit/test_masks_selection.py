import numpy as np
import pytest

from image_studio.core.color import f_to_u8
from image_studio.errors import ValidationError


def test_selection_modes(editor, doc):
    editor.create_selection(doc, "rectangle", x=0, y=0, width=100, height=120)
    r = editor.create_selection(doc, "rectangle", x=50, y=0, width=100, height=120, mode="intersect")
    assert r["selection"]["bounds"] == [50, 0, 50, 120]
    r = editor.modify_selection(doc, "invert")
    assert r["selection"]["selected_fraction"] == pytest.approx(0.75, abs=0.01)
    r = editor.modify_selection(doc, "clear")
    assert r["selection"] is None


def test_select_by_color_contiguous(editor, doc):
    lid = editor.create_layer(doc, "paint", fill_color="#000000")["layer_id"]
    editor.create_shape_layer(doc, "rectangle", 10, 10, 20, 20, fill="#ffffff")
    editor.create_shape_layer(doc, "rectangle", 100, 10, 20, 20, fill="#ffffff")
    merged = editor.merge_down(doc, editor.list_layers(doc)["layers"][0]["id"])
    merged = editor.merge_down(doc, editor.list_layers(doc)["layers"][0]["id"])["layer_id"]
    r = editor.select_by_color(doc, merged, point=[15, 15], tolerance=20, contiguous=True)
    x, y, w, h = r["selection"]["bounds"]
    assert x >= 9 and x + w <= 31
    r = editor.select_by_color(doc, merged, color="#ffffff", tolerance=20)
    assert r["selection"]["bounds"][2] > 100
    assert lid


def test_layer_mask_lifecycle(editor, doc):
    lid = editor.create_layer(doc, "top", fill_color="#ff0000")["layer_id"]
    editor.create_layer_mask(doc, lid, "black")
    c = f_to_u8(editor.render_doc(editor.project(doc)))
    assert tuple(c[60, 100, :3]) == (128, 128, 128)
    editor.edit_layer_mask(doc, lid, "paint", value=1.0, strokes=[[[100, 60]]], brush_size=20, hardness=1.0)
    c = f_to_u8(editor.render_doc(editor.project(doc)))
    assert c[60, 100, 0] > 250 and c[10, 10, 0] == 128
    editor.invert_mask(doc, lid)
    c = f_to_u8(editor.render_doc(editor.project(doc)))
    assert c[10, 10, 0] > 250 and c[60, 100, 0] == 128
    editor.feather_mask(doc, lid, 6)
    editor.set_mask_enabled(doc, lid, False)
    assert f_to_u8(editor.render_doc(editor.project(doc)))[60, 100, 0] > 250
    editor.set_mask_enabled(doc, lid, True)
    editor.apply_mask(doc, lid)
    info = editor.get_layer_info(doc, lid)["layer"]
    assert not info["has_mask"]
    proj = editor.project(doc)
    alpha = proj.blobs.get(proj.doc.layers[lid].pixels)[..., 3]
    assert alpha[60, 100] < 50 and alpha[10, 10] == 255


def test_gradient_mask(editor, doc):
    lid = editor.create_layer(doc, "top", fill_color="#ffffff")["layer_id"]
    editor.create_layer_mask(doc, lid, "linear_gradient", start=[0, 0], end=[200, 0])
    m = editor.project(doc).blobs.get(editor.project(doc).doc.layers[lid].mask.blob)
    assert m[0, 0] > 250 and m[0, 199] < 5 and 110 < m[0, 100] < 145


def test_mask_errors(editor, doc):
    lid = editor.create_layer(doc, "x")["layer_id"]
    with pytest.raises(ValidationError):
        editor.invert_mask(doc, lid)
    with pytest.raises(ValidationError):
        editor.create_layer_mask(doc, lid, "selection")  # no selection
    editor.create_layer_mask(doc, lid)
    with pytest.raises(ValidationError):
        editor.create_layer_mask(doc, lid)


def test_adjust_inside_selection_only(editor, doc):
    lid = editor.create_layer(doc, "p", fill_color="#808080")["layer_id"]
    editor.create_selection(doc, "rectangle", x=0, y=0, width=50, height=50)
    editor.adjust_colors(doc, lid, "invert", use_selection=True)
    arr = editor.project(doc).blobs.get(editor.project(doc).doc.layers[lid].pixels)
    assert arr[10, 10, 0] == 127 and arr[100, 150, 0] == 128
    assert np.all(arr[..., 3] == 255)
