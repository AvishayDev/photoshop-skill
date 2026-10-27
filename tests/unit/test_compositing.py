import numpy as np
import pytest

from image_studio.core.blending import blend_function, composite
from image_studio.core.color import f_to_u8
from image_studio.core.layer import BlendMode


def px(rgb, a=1.0):
    out = np.zeros((1, 1, 4), np.float32)
    out[..., :3] = rgb
    out[..., 3] = a
    return out


@pytest.mark.parametrize("mode,cb,cs,expected", [
    (BlendMode.multiply, 0.5, 0.5, 0.25),
    (BlendMode.screen, 0.5, 0.5, 0.75),
    (BlendMode.darken, 0.3, 0.6, 0.3),
    (BlendMode.lighten, 0.3, 0.6, 0.6),
    (BlendMode.difference, 0.8, 0.3, 0.5),
    (BlendMode.overlay, 0.25, 0.5, 0.25),
    (BlendMode.linear_dodge, 0.6, 0.6, 1.0),
    (BlendMode.subtract, 0.6, 0.2, 0.4),
])
def test_blend_formulas(mode, cb, cs, expected):
    out = blend_function(mode, np.full((1, 3), cb, np.float32), np.full((1, 3), cs, np.float32))
    assert out[0, 0] == pytest.approx(expected, abs=1e-5)


def test_normal_with_opacity_and_mask():
    back = px([0, 0, 0])
    src = px([1, 1, 1])
    assert composite(back, src, opacity=0.5)[0, 0, 0] == pytest.approx(0.5)
    assert composite(back, src, mask=np.array([[0.25]], np.float32))[0, 0, 0] == pytest.approx(0.25)


def test_transparent_backdrop_takes_source_color():
    out = composite(px([0, 0, 0], 0.0), px([0.2, 0.4, 0.6], 1.0), BlendMode.multiply)
    assert out[0, 0, :3] == pytest.approx([0.2, 0.4, 0.6], abs=1e-5)


def test_luminosity_modes_preserve_lum():
    cb = np.array([[0.8, 0.2, 0.2]], np.float32)
    cs = np.array([[0.1, 0.1, 0.9]], np.float32)
    from image_studio.core.color import luminance
    out = blend_function(BlendMode.color, cb, cs)
    assert luminance(out)[0] == pytest.approx(luminance(cb)[0], abs=1e-3)


def test_document_composite_with_mask_and_clipping(editor, doc):
    red = editor.create_layer(doc, "Red", fill_color="#ff0000")["layer_id"]
    editor.create_selection(doc, "rectangle", x=0, y=0, width=100, height=120)
    editor.create_layer_mask(doc, red, "selection")
    blue = editor.create_layer(doc, "Blue clip", fill_color="#0000ff")["layer_id"]
    editor.set_layer_properties(doc, blue, clipped=True, opacity=0.5)
    canvas = f_to_u8(editor.render_doc(editor.project(doc)))
    left, right = canvas[60, 50], canvas[60, 150]
    assert tuple(right[:3]) == (128, 128, 128)  # mask hides red, clip hides blue
    assert left[0] > 120 and left[2] > 120 and left[1] < 10  # red with half blue on top


def test_adjustment_layer_non_destructive(editor, doc):
    adj = editor.create_adjustment_layer(doc, "invert")["layer_id"]
    canvas = f_to_u8(editor.render_doc(editor.project(doc)))
    assert tuple(canvas[0, 0, :3]) == (127, 127, 127)
    editor.update_adjustment_layer(doc, adj, {})
    editor.set_layer_visibility(doc, adj, False)
    assert tuple(f_to_u8(editor.render_doc(editor.project(doc)))[0, 0, :3]) == (128, 128, 128)


def test_group_isolation_and_pass_through(editor, doc):
    a = editor.create_layer(doc, "white", fill_color="#ffffff")["layer_id"]
    g = editor.create_group(doc, "G", [a], blend_mode="normal")["group_id"]
    editor.set_layer_properties(doc, a, blend_mode="multiply")
    # isolated group: multiply against transparent -> pure white over gray
    c1 = f_to_u8(editor.render_doc(editor.project(doc)))[5, 5, :3]
    editor.set_layer_properties(doc, g, blend_mode="pass_through")
    c2 = f_to_u8(editor.render_doc(editor.project(doc)))[5, 5, :3]
    assert tuple(c1) == (255, 255, 255)
    assert tuple(c2) == (128, 128, 128)  # multiply by white on gray


def test_layer_effect_drop_shadow(editor, doc):
    s = editor.create_shape_layer(doc, "rectangle", 50, 30, 40, 40, fill="#ffffff")["layer_id"]
    editor.add_layer_effect(doc, s, "drop_shadow", {"distance": 15, "size": 2, "opacity": 1.0, "direction_deg": 0})
    canvas = f_to_u8(editor.render_doc(editor.project(doc)))
    assert canvas[50, 100, 0] < 60  # shadow right of the shape
    assert canvas[50, 40, 0] == 128


def test_effect_validation(editor, doc):
    from image_studio.errors import ValidationError
    lid = editor.list_layers(doc)["layers"][0]["id"]
    with pytest.raises(ValidationError):
        editor.add_layer_effect(doc, lid, "drop_shadow", {"bogus": 1})


def test_clipped_adjustments_stack_in_call_order(editor, doc):
    s = editor.create_layer(doc, "subject", fill_color="#808080")["layer_id"]
    a = editor.adjust_colors(doc, s, "invert", as_adjustment_layer=True)["layer_id"]
    b = editor.adjust_colors(doc, s, "brightness_contrast", {"brightness": 0.2}, as_adjustment_layer=True)["layer_id"]
    order = [x["id"] for x in editor.list_layers(doc)["layers"]]
    assert order.index(b) < order.index(a) < order.index(s)  # top -> bottom: b above a above subject
