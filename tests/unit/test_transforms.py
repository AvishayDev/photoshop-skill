import numpy as np
import pytest

from image_studio.core.color import f_to_u8
from image_studio.errors import ValidationError


def _rect(editor, doc, x=40, y=30, w=40, h=20, color="#ff0000"):
    return editor.create_shape_layer(doc, "rectangle", x, y, w, h, fill=color)["layer_id"]


def _bbox(editor, doc, lid):
    return editor.get_layer_info(doc, lid)["layer"]["opaque_bounds_document"]


def test_translate_is_lossless(editor, doc):
    lid = _rect(editor, doc)
    before = editor.project(doc).blobs.get(editor.project(doc).doc.layers[lid].pixels)
    editor.transform_layer(doc, lid, translate_x=10, translate_y=-5)
    after = editor.project(doc).blobs.get(editor.project(doc).doc.layers[lid].pixels)
    assert np.array_equal(before, after)
    assert _bbox(editor, doc, lid)[:2] == [50, 25]


def test_scale_about_center(editor, doc):
    lid = _rect(editor, doc)
    editor.transform_layer(doc, lid, scale_x=2.0)
    x, y, w, h = _bbox(editor, doc, lid)
    assert abs(w - 80) <= 2 and abs(h - 40) <= 2
    assert abs((x + w / 2) - 60) <= 1.5 and abs((y + h / 2) - 40) <= 1.5


def test_rotate_90(editor, doc):
    lid = _rect(editor, doc)
    editor.rotate_layer(doc, lid, 90)
    x, y, w, h = _bbox(editor, doc, lid)
    assert abs(w - 20) <= 2 and abs(h - 40) <= 2


def test_smart_transform_no_cumulative_loss(editor, doc, photo):
    lid = editor.import_image_as_layer(doc, path=str(photo), x=0, y=0)["layer_id"]
    proj = editor.project(doc)
    orig = proj.blobs.get(proj.doc.layers[lid].pixels).astype(int)
    for _ in range(6):
        editor.rotate_layer(doc, lid, 30)
    proj = editor.project(doc)
    layer = proj.doc.layers[lid]
    arr = proj.blobs.get(layer.pixels)
    h, w = orig.shape[:2]
    # after 180 degrees total the content should be the original flipped both ways
    cx, cy = arr.shape[1] // 2, arr.shape[0] // 2
    crop = arr[cy - 30:cy + 30, cx - 60:cx + 60, :3].astype(int)
    ref = orig[::-1, ::-1][h // 2 - 30:h // 2 + 30, w // 2 - 60:w // 2 + 60, :3]
    best = min(np.abs(np.roll(crop, (dy, dx), (0, 1)) - ref)[3:-3, 3:-3].mean()
               for dy in range(-2, 3) for dx in range(-2, 3))
    assert best < 4  # re-rendered from the source once, not resampled 6 times
    assert layer.base_blob is not None and layer.transform is not None


def test_flip(editor, doc):
    lid = _rect(editor, doc, x=10, w=20)
    editor.create_shape_layer(doc, "rectangle", 10, 30, 5, 20, fill="#00ff00")
    editor.flip_layer(doc, lid, "horizontal")
    assert _bbox(editor, doc, lid)[0] == 10


def test_perspective(editor, doc):
    lid = _rect(editor, doc, 0, 0, 100, 50)
    editor.transform_layer(doc, lid, perspective=[[20, 10], [120, 20], [110, 80], [30, 70]])
    x, y, w, h = _bbox(editor, doc, lid)
    assert 18 <= x <= 22 and 8 <= y <= 12 and 95 <= w <= 103


def test_align(editor, doc):
    a = _rect(editor, doc, 5, 5, 10, 10)
    editor.align_layers(doc, [a], "right")
    assert _bbox(editor, doc, a)[0] + 10 == 200
    editor.align_layers(doc, [a], "middle")
    assert _bbox(editor, doc, a)[1] == 55


def test_crop_and_resize(editor, doc):
    lid = _rect(editor, doc, 40, 30, 40, 20)
    editor.crop_image(doc, 20, 10, 100, 80)
    info = editor.get_document_info(doc)["document"]
    assert (info["width"], info["height"]) == (100, 80)
    assert _bbox(editor, doc, lid)[:2] == [20, 20]
    editor.resize_image(doc, width=50)
    info = editor.get_document_info(doc)["document"]
    assert (info["width"], info["height"]) == (50, 40)
    canvas = f_to_u8(editor.render_doc(editor.project(doc)))
    assert canvas.shape[:2] == (40, 50)


def test_crop_validation(editor, doc):
    with pytest.raises(ValidationError):
        editor.crop_image(doc, 150, 0, 100, 50)


def test_identity_transform_rejected(editor, doc):
    lid = _rect(editor, doc)
    with pytest.raises(ValidationError):
        editor.transform_layer(doc, lid)
