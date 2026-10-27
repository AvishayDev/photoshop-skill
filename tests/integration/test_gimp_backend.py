"""Integration tests against a real GIMP 3 installation.

Skipped (with a reason) when GIMP 3 is not installed. Point IMAGE_STUDIO_GIMP at
the executable/AppImage to run them, e.g.
IMAGE_STUDIO_GIMP=/path/to/GIMP-3.2.2-x86_64.AppImage pytest -m gimp
"""

import numpy as np
import pytest

from tests.conftest import gimp_available

pytestmark = [pytest.mark.gimp]


@pytest.fixture(autouse=True)
def _need_gimp(settings):
    if not gimp_available():
        pytest.skip("GIMP 3.x not available (set IMAGE_STUDIO_GIMP); native backend tests skipped")


def test_probe_lists_gegl_operations():
    from image_studio.backends.gimp import GimpBackend
    ops = GimpBackend().filters()
    assert "gegl:gaussian-blur" in ops and len(ops) > 50


def test_native_gegl_filter(editor, doc):
    lid = editor.create_shape_layer(doc, "rectangle", 50, 30, 60, 40, fill="#ffffff")["layer_id"]
    editor.rasterize_layer(doc, lid)
    r = editor.apply_filter(doc, lid, "gegl:gaussian-blur", {"std-dev-x": 4.0, "std-dev-y": 4.0})
    assert r["backend"] == "gimp"
    arr = editor.project(doc).blobs.get(editor.project(doc).doc.layers[lid].pixels)
    edge = arr[arr.shape[0] // 2, :, 3]
    assert 0 < edge[2] < 255  # soft alpha ramp produced by GEGL


def test_native_clone_and_heal(editor, photo):
    d = editor.open_document(str(photo))["document_id"]
    work = editor.duplicate_layer(d, editor.list_layers(d)["layers"][0]["id"])["layer_id"]
    r = editor.clone_stamp(d, work, source_point=[30, 100], strokes=[[[100, 60], [104, 60]]], brush_size=12,
                           hardness=1.0, backend="gimp")
    assert r["backend"] == "gimp" and r["details"]["native_tool"] == "gimp-clone"
    arr = editor.project(d).blobs.get(editor.project(d).doc.layers[work].pixels)
    assert arr[60, 100, 0] < 160
    r = editor.heal_region(d, work, strokes=[[[100, 50]]], source_point=[40, 20], brush_size=20, backend="gimp")
    assert r["details"]["native_tool"] == "gimp-heal"


def test_xcf_roundtrip_preserves_layers_masks_modes(editor, doc):
    a = editor.create_shape_layer(doc, "ellipse", 30, 20, 80, 60, fill="#ff3300")["layer_id"]
    editor.set_layer_properties(doc, a, blend_mode="multiply", opacity=0.8)
    editor.create_layer_mask(doc, a, "linear_gradient", start=[30, 0], end=[110, 0])
    editor.create_group(doc, "Subject", [a])
    r = editor.save_document(doc, "xcf")
    assert r["native_file"].endswith(".xcf") and r["size_bytes"] > 0
    before = editor.render_doc(editor.project(doc))
    d2 = editor.open_document(r["native_file"], name="xcf back")["document_id"]
    layers = editor.list_layers(d2)["layers"]
    names = [x["name"] for x in layers]
    assert "Subject" in names and "Ellipse" in names
    ell = next(x for x in layers if x["name"] == "Ellipse")
    assert ell["has_mask"] and ell["blend_mode"] == "multiply" and abs(ell["opacity"] - 0.8) < 0.01
    after = editor.render_doc(editor.project(d2))
    assert np.abs(before - after).mean() < 0.01
