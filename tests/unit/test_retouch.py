import numpy as np
import pytest

from image_studio.core import retouch
from image_studio.errors import ValidationError


def test_clone_stamp_core_deterministic():
    tgt = np.zeros((50, 50, 4), np.uint8)
    tgt[..., 3] = 255
    src = tgt.copy()
    src[30:40, 30:40, :3] = 255
    out, info = retouch.clone_stamp(tgt, src, (35, 35), [[[10, 10]]], size=6, hardness=1.0)
    assert out[10, 10, 0] == 255 and out[20, 20, 0] == 0
    out2, _ = retouch.clone_stamp(tgt, src, (35, 35), [[[10, 10]]], size=6, hardness=1.0)
    assert np.array_equal(out, out2)
    assert info["offset"] == [25.0, 25.0]


def test_clone_aligned_vs_not():
    tgt = np.zeros((60, 60, 4), np.uint8)
    tgt[..., 3] = 255
    src = tgt.copy()
    src[:, 40:, :3] = 200
    strokes = [[[5, 5]], [[5, 30]]]
    a, _ = retouch.clone_stamp(tgt, src, (45, 5), strokes, size=4, hardness=1, aligned=True)
    b, _ = retouch.clone_stamp(tgt, src, (45, 5), strokes, size=4, hardness=1, aligned=False)
    assert a[30, 5, 0] == 200 and b[30, 5, 0] == 200


def test_clone_stamp_editor(editor, photo):
    d = editor.open_document(str(photo))["document_id"]
    orig = editor.list_layers(d)["layers"][0]["id"]
    work = editor.duplicate_layer(d, orig, "Retouch")["layer_id"]
    r = editor.clone_stamp(d, work, source_point=[30, 100], strokes=[[[100, 60], [110, 60]]], brush_size=16,
                           hardness=0.8)
    assert r["backend"] == "pillow" and r["details"]["dabs_painted"] > 0
    arr = editor.project(d).blobs.get(editor.project(d).doc.layers[work].pixels)
    assert arr[60, 100, 0] < 150  # red disc pixel replaced by ground texture
    with pytest.raises(ValidationError):
        editor.clone_stamp(d, work, source_point=[500, 500], strokes=[[[1, 1]]])


def test_heal_and_spot_heal(editor, photo):
    d = editor.open_document(str(photo))["document_id"]
    work = editor.duplicate_layer(d, editor.list_layers(d)["layers"][0]["id"])["layer_id"]
    r = editor.heal_region(d, work, strokes=[[[100, 60]]], source_point=[40, 30], brush_size=50)
    assert r["details"]["method"] == "poisson_clone"
    r = editor.heal_region(d, work, strokes=[[[20, 100]]], brush_size=10)
    assert r["details"]["method"] == "inpaint_telea"


def test_remove_object_from_selection(editor, photo):
    d = editor.open_document(str(photo))["document_id"]
    work = editor.duplicate_layer(d, editor.list_layers(d)["layers"][0]["id"])["layer_id"]
    editor.create_selection(d, "ellipse", x=78, y=38, width=44, height=44)
    r = editor.remove_object(d, work)
    arr = editor.project(d).blobs.get(editor.project(d).doc.layers[work].pixels)
    assert arr[60, 100, 0] < 160 and arr[60, 100, 2] > 120  # red gone, sky-like
    assert r["region_fraction"] > 0


def test_remove_background_grabcut_makes_mask(editor, tmp_path):
    from PIL import Image
    img = np.full((100, 100, 3), (40, 160, 60), np.uint8)
    yy, xx = np.mgrid[0:100, 0:100]
    img[(xx - 50) ** 2 + (yy - 50) ** 2 < 25 ** 2] = (220, 40, 40)
    p = tmp_path / "subject.png"
    Image.fromarray(img).save(p)
    d = editor.open_document(str(p))["document_id"]
    lid = editor.list_layers(d)["layers"][0]["id"]
    r = editor.remove_background(d, lid, rect=[15, 15, 70, 70])
    assert 0.12 < r["subject_fraction"] < 0.28
    proj = editor.project(d)
    layer = proj.doc.layers[lid]
    assert layer.mask is not None
    assert np.array_equal(proj.blobs.get(layer.pixels)[..., :3], img)  # pixels untouched
    m = proj.blobs.get(layer.mask.blob)
    assert m[50, 50] > 200 and m[5, 5] < 30
    r = editor.remove_background(d, lid, method="color_key", color="#28a03c", tolerance=30)
    assert r["subject_fraction"] < 0.3


def test_filters_and_adjustments(editor, doc):
    lid = editor.create_layer(doc, "p", fill_color="#406080")["layer_id"]
    for name, params in [("gaussian_blur", {"radius": 3}), ("unsharp_mask", {}), ("add_noise", {"amount": 0.02}),
                         ("vignette", {}), ("motion_blur", {"distance": 9, "angle": 30})]:
        assert editor.apply_filter(doc, lid, name, params)["ok"]
    for adj, params in [("brightness_contrast", {"brightness": 0.1}), ("curves", {"points": [[0, 0], [128, 150], [255, 255]]}),
                        ("hue_saturation", {"hue": 20}), ("levels", {"in_black": 10}), ("exposure", {"ev": 0.5}),
                        ("temperature_tint", {"temperature": 0.3}), ("color_balance", {"midtones": [0.1, 0, -0.1]})]:
        assert editor.adjust_colors(doc, lid, adj, params)["ok"]
    with pytest.raises(ValidationError):
        editor.apply_filter(doc, lid, "gaussian_blur", {"radius": -1})
    with pytest.raises(ValidationError):
        editor.adjust_colors(doc, lid, "curves", {"points": [[0, 0]]})
    with pytest.raises(ValidationError):
        editor.apply_filter(doc, lid, "nonexistent")


def test_match_color(editor, doc):
    editor.create_layer(doc, "warm bg", fill_color="#c08040")
    s = editor.create_shape_layer(doc, "ellipse", 60, 30, 60, 60, fill="#4060c0")["layer_id"]
    r = editor.match_color(doc, s, strength=1.0)
    assert r["ok"] and r["measurements"]["reference_lab_mean"][2] > r["measurements"]["subject_lab_mean"][2]
