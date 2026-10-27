"""Procedural painting engine, pattern learning/library and pipelines."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from image_studio.errors import ValidationError
from image_studio.paint import brush, canvas, figure, noise, patterns, scene, shading, shapes, synthesis
from image_studio.patterns import PatternEntry, PatternLibrary, learn_from_image
from image_studio.pipeline import Pipeline, run_spec

REPO = Path(__file__).resolve().parents[2]
REPO_LIBRARY = PatternLibrary(REPO / "knowledge" / "patterns")

PLAN = [
    "Search the pattern library and knowledge base for the subject and the environment",
    "Research reference images of the subject and study its silhouette and markings",
    "Measure the subject's stripe pattern and palette from a reference with learn_pattern",
    "Define the composition, horizon height and key light direction for the scene",
    "Paint the sky gradient with a warm glow around the low sun",
    "Paint the ground plane with perspective texture toward the horizon",
    "Generate the subject from the figure recipe and learned patterns",
    "Blend the subject into the scene with contact and cast shadows",
    "Apply a colour grade and vignette with adjustment layers",
    "Render a preview, inspect it and export the final image with a report",
]


# ----- primitives --------------------------------------------------------------------------------

def test_smoothstep_handles_falling_edges():
    x = np.array([0.0, 5.0, 10.0], np.float32)
    assert canvas.smoothstep(0, 10, x).tolist() == [0.0, 0.5, 1.0]
    assert canvas.smoothstep(10, 0, x).tolist() == [1.0, 0.5, 0.0]


def test_over_and_place():
    a = canvas.solid(4, 4, "#ff0000")
    b = canvas.solid(4, 4, "#0000ff", 0.5)
    out = canvas.over(a, b)
    assert out[0, 0, 3] == pytest.approx(1.0)
    assert out[0, 0, 0] == pytest.approx(0.5, abs=1e-3) and out[0, 0, 2] == pytest.approx(0.5, abs=1e-3)
    placed = canvas.place(canvas.solid(3, 3, "#ffffff"), 6, 6, 4, -1)
    assert placed[..., 3].sum() == pytest.approx(4)  # clipped to 2x2


def test_tileable_noise_is_seamless_and_seeded():
    t = noise.tileable_fbm(128, 32, 4, seed=3)
    assert t.shape == (128, 128) and 0 <= t.min() and t.max() <= 1
    edge = np.abs(t[0] - t[-1]).mean()
    inner = np.abs(t[0] - t[1]).mean()
    assert edge < inner * 2.5
    assert np.array_equal(noise.fbm(64, 48, 16, seed=1), noise.fbm(64, 48, 16, seed=1))


def test_shapes_are_antialiased_masks():
    m = shapes.ellipse(64, 64, 32, 32, 20, 10)
    assert m.max() == 1.0 and m[0, 0] == 0.0
    assert 0 < m[32, 12] < 1 or 0 < m[32, 11] < 1 or 0 < m[32, 13] < 1  # soft edge
    c = shapes.capsule(64, 64, (10, 10), (50, 50), 6, 3)
    assert c[30, 30] == 1.0 and c[5, 60] == 0.0
    b = shapes.bent_capsule(64, 64, [(10, 50), (30, 20), (50, 50)], [5, 3])
    assert b.sum() > 100


def test_shading_lights_the_side_facing_the_light():
    alpha = shapes.ellipse(80, 80, 40, 40, 30, 30)
    base = np.full((80, 80, 3), 0.6, np.float32)
    lit = shading.shade(base, alpha, azimuth=180, elevation=20, ambient=0.2, occlusion=0)
    assert lit[40, 18].mean() > lit[40, 62].mean()  # light from the left


def test_stripes_and_spots_cover_expected_fraction():
    s = patterns.stripes(200, 100, period=20, thickness=0.4, breakup=0.0, seed=1)
    assert 0.2 < (s > 0.5).mean() < 0.6
    sp = patterns.spots(200, 100, size=10, seed=1)
    assert 0.02 < (sp > 0.5).mean() < 0.4
    eye = patterns.eyespot(10)
    assert eye.shape[2] == 4 and eye[..., 3].max() == pytest.approx(1.0, abs=1e-3)


def test_brush_stroke_and_fur():
    c = canvas.blank(60, 40)
    brush.stroke(c, [(5, 20), (30, 10), (55, 20)], "#ff0000", size=8)
    assert c[..., 3].max() > 0.9 and c[0, 0, 3] == 0
    painted = canvas.solid(60, 40, "#c06020")
    m = shapes.ellipse(60, 40, 30, 20, 20, 12)
    f = brush.fur(painted, m, 0.0, density=0.2, length=5, seed=1)
    assert f.shape == (40, 60, 4) and f[20, 30, 3] == pytest.approx(1.0)


@pytest.mark.parametrize("builder", [
    lambda: scene.sky(96, 64, horizon_y=40, sun=(70, 38)),
    lambda: scene.clouds(96, 64, top=5, bottom=35, seed=1),
    lambda: scene.mountains(96, 64, base_y=45, peak=20),
    lambda: scene.ground(96, 64, horizon_y=30),
    lambda: scene.ocean(96, 64, horizon_y=25, sun_x=60),
    lambda: scene.light_rays(96, 64, origin=(10, -5)),
    lambda: scene.haze(96, 64, horizon_y=30),
    lambda: scene.dapples(96, 64, stretch=2),
    lambda: brush.grass(96, 64, top=40, bottom=64, density=0.02),
])
def test_scene_builders_return_canvas_layers(builder):
    out = builder()
    assert out.shape == (64, 96, 4) and out.dtype == np.float32
    assert out[..., 3].max() > 0 and np.isfinite(out).all()


def test_forest_returns_named_depth_layers():
    layers = scene.forest(160, 100, horizon_y=60, depth_layers=2, trees_per_layer=3, trunk_width=12, seed=1)
    assert [n for n, _ in layers][0] == "far wall" and len(layers) == 3
    assert all(lay[..., 3].max() > 0 for _, lay in layers)


def test_quilting_synthesizes_larger_texture():
    rng = np.random.default_rng(0)
    ex = rng.random((40, 40, 3)).astype(np.float32)
    out = synthesis.quilt(ex, 90, 70, patch=20, seed=1)
    assert out.shape == (70, 90, 3)
    with pytest.raises(ValidationError):
        synthesis.quilt(ex[:6, :6], 50, 50)


# ----- figures ------------------------------------------------------------------------------------

@pytest.mark.parametrize("pid", ["figure/tiger-walking", "figure/peacock-standing"])
def test_library_figures_render(pid, monkeypatch):
    spec = REPO_LIBRARY.get(pid).params
    monkeypatch.setattr("image_studio.patterns.library.PatternLibrary.__init__",
                        lambda self, root=None: setattr(self, "root", REPO_LIBRARY.root))
    left = figure.render_figure(spec, height=60, facing="left", seed=1)
    right = figure.render_figure(spec, height=60, facing="right", seed=1)
    assert left[..., 3].mean() > 0.1
    assert np.allclose(left[..., 3], right[:, ::-1, 3])


def test_figure_rejects_unknown_shapes():
    with pytest.raises(ValidationError):
        figure.render_figure({"parts": [{"shape": "cube"}]}, height=40)


# ----- learning & library -------------------------------------------------------------------------

def _striped_subject() -> np.ndarray:
    h, w = 160, 240
    img = np.zeros((h, w, 4), np.uint8)
    img[...] = (40, 90, 40, 255)  # green background
    yy, xx = np.mgrid[0:h, 0:w]
    body = ((xx - 120) / 90.0) ** 2 + ((yy - 80) / 50.0) ** 2 < 1
    img[body] = (220, 130, 40, 255)
    img[body & ((xx // 12) % 2 == 0)] = (25, 20, 15, 255)  # vertical stripes, period 24 px
    return img


def test_learn_detects_stripes_period_and_silhouette():
    res = learn_from_image(_striped_subject(), rect=[20, 20, 200, 120], name="test")
    assert res["marks"]["type"] == "stripes"
    assert res["period"]["period_px"] == pytest.approx(24, rel=0.15)
    assert res["silhouette"]["aspect"] == pytest.approx(1.8, rel=0.15)
    ids = [s["id"] for s in res["suggested"]]
    assert "texture/test-stripes" in ids and "silhouette/test" in ids
    json.dumps(res)  # serializable


def test_learn_texture_mode_without_subject():
    res = learn_from_image(_striped_subject()[40:120, 60:180, :3])
    assert res["mode"] == "texture" and "silhouette" not in res


def test_pattern_library_roundtrip(tmp_path):
    lib = PatternLibrary(tmp_path / "patterns")
    lib.save(PatternEntry(id="texture/zebra-stripes", kind="texture", title="Zebra stripes",
                          tags=["zebra", "stripes"], params={"type": "stripes", "period": 0.06}))
    assert lib.get("texture/zebra-stripes").params["period"] == 0.06
    assert lib.search("zebra")[0]["id"] == "texture/zebra-stripes"
    with pytest.raises(ValidationError):
        lib.save(PatternEntry(id="texture/zebra-stripes", kind="texture", title="dup"), overwrite=False)
    with pytest.raises(ValidationError):
        lib.save(PatternEntry(id="bad/x", kind="bad", title="x"))
    with pytest.raises(ValidationError):
        lib.save(PatternEntry(id="palette/p", kind="palette", title="p", confidence="high"))


def test_repository_library_entries_are_valid():
    entries = REPO_LIBRARY.all()
    ids = {e.id for e in entries}
    assert {"figure/tiger-walking", "figure/peacock-standing", "texture/tiger-stripes"} <= ids
    for e in entries:
        assert e.id.startswith(e.kind + "/") and e.sources, e.id


# ----- pipelines ----------------------------------------------------------------------------------

def test_pipeline_requires_ten_step_plan(editor):
    with pytest.raises(ValidationError):
        Pipeline("Create a cat", ["Paint the cat on the canvas"] * 3, size=(64, 48), editor=editor, verbose=False)


def test_pipeline_builds_layered_project(editor):
    p = Pipeline("Create a sunset over hills", PLAN, size=(120, 80), editor=editor, verbose=False, seed=2)
    with p.step(5):
        p.add("Sky", scene.sky(120, 80, horizon_y=50, sun=(90, 48)), group="Environment")
    with p.step(6):
        p.add("Ground", scene.ground(120, 80, horizon_y=50), group="Environment")
    with p.step(7):
        disc = canvas.solid(120, 80, "#aa3311", shapes.ellipse(120, 80, 60, 55, 12, 10))
        p.add("Subject", disc)
    with p.step(8):
        p.contact_shadow("Subject contact", "Subject", opacity=0.6)
        p.cast_shadow("Subject shadow", "Subject", azimuth=200, elevation=30)
        p.reflection("Subject reflection", "Subject", axis_y=65)
        p.rim_light("Subject rim", "Subject", azimuth=200)
    with p.step(9):
        p.adjust("Warm", "temperature_tint", {"temperature": 0.2})
    with p.step(10):
        rep = p.finish(formats=("png",))
    assert Path(rep["exports"][0]).exists() and Path(rep["layered_file"]).exists()
    assert rep["plan_steps_not_marked"] == [1, 2, 3, 4]
    data = json.loads((Path(rep["project_path"]) / "pipeline.json").read_text())
    assert any(lay["layer"] == "Subject rim" for lay in data["layers"])
    names = {lay.name for lay in editor.project(rep["document_id"]).doc.layers.values()}
    assert {"Environment", "Sky", "Subject", "Subject shadow", "Warm"} <= names
    with pytest.raises(ValidationError):
        with p.step(99):
            pass


def test_run_spec_and_errors(editor):
    spec = {"request": "Create a calm sea at dusk", "plan": PLAN, "size": [96, 64], "name": "spec test",
            "steps": [{"step": 5, "action": "sky", "name": "Sky", "params": {"horizon_y": 30}},
                      {"step": 6, "action": "ocean", "name": "Sea", "params": {"horizon_y": 30, "sun_x": 50}},
                      {"step": 7, "action": "shape", "name": "Rock", "params": {
                          "shape": "ellipse", "cx": 40, "cy": 45, "rx": 10, "ry": 5, "color": "#222222"}},
                      {"step": 8, "action": "reflection", "name": "Rock reflection",
                       "params": {"of": "Rock", "axis_y": 50}},
                      {"step": 10, "action": "preview", "params": {"tag": "check"}}],
            "formats": ["png"], "save_ora": False}
    rep = run_spec(spec, editor=editor)
    assert any("check" in pth for pth in rep["previews"])
    bad = dict(spec, steps=[{"step": 5, "action": "teleport"}])
    with pytest.raises(ValidationError):
        run_spec(bad, editor=editor)
    bad = dict(spec, steps=[{"step": 5, "action": "sky", "params": {"nonsense": 1}}])
    with pytest.raises(ValidationError):
        run_spec(bad, editor=editor)


def test_color_balance_range_is_enforced():
    from image_studio.core.adjustments import validate_params
    with pytest.raises(ValidationError):
        validate_params("color_balance", {"shadows": [-6, 2, 8]})
    assert validate_params("color_balance", {"shadows": [-0.1, 0, 0.1]})["shadows"] == [-0.1, 0.0, 0.1]


# ----- MCP tools ----------------------------------------------------------------------------------

def test_mcp_painting_tools(settings, tmp_path):
    from PIL import Image

    from image_studio.mcp_server.server import create_server
    from image_studio.mcp_server.session import Session
    from tests.unit.test_mcp_server import call

    server = create_server(Session())
    data, err = call(server, "list_paint_actions", {})
    assert not err and {"sky", "ocean", "forest", "figure", "reflection"} <= set(data["actions"])
    data, err = call(server, "submit_plan", {"request": "Create a sunset over the sea", "steps": PLAN})
    assert not err
    doc = call(server, "create_project", {"name": "Paint", "width": 96, "height": 64,
                                          "background": None})[0]["document_id"]
    data, err = call(server, "paint_layer", {"document_id": doc, "action": "sky", "name": "Sky",
                                             "params": {"horizon_y": 30, "sun": [70, 28]}})
    assert not err and data["layer_ids"]
    data, err = call(server, "paint_layer", {"document_id": doc, "action": "shape", "name": "Rock",
                                             "params": {"shape": "ellipse", "cx": 40, "cy": 45, "rx": 8, "ry": 4}})
    assert not err
    data, err = call(server, "paint_layer", {"document_id": doc, "action": "cast_shadow", "name": "Rock shadow",
                                             "params": {"of": "Rock", "azimuth": 200, "elevation": 30}})
    assert not err
    data, err = call(server, "paint_layer", {"document_id": doc, "action": "teleport"})
    assert err and data["error"]["code"] == "invalid_parameter"

    # learn_pattern + synthesize_texture from a CC0 reference stored in the project
    proj = Session().editor.project(doc)
    Image.fromarray(_striped_subject()).save(proj.root / "references" / "ref_test.png")
    (proj.root / "references" / "ref_test.json").write_text(json.dumps({
        "id": "ref_test", "local_path": "references/ref_test.png", "title": "Striped test",
        "source_page": "https://example.org/striped", "license": {"short_name": "CC0 1.0"}}))
    data, err = call(server, "learn_pattern", {"document_id": doc, "reference_id": "ref_test", "name": "striped",
                                               "rect": [20, 20, 200, 120]})
    assert not err and data["marks"]["type"] == "stripes" and Path(data["saved_to"]).exists()
    assert data["suggested"][0]["sources"][0]["url"] == "https://example.org/striped"
    data, err = call(server, "synthesize_texture", {"document_id": doc, "reference_id": "ref_test",
                                                    "rect": [40, 40, 80, 60], "width": 96, "height": 30,
                                                    "y": 34, "patch": 24})
    assert not err and data["layer_id"]

    data, err = call(server, "save_pattern", {"pattern_id": "texture/striped-test", "title": "Striped test",
                                              "params": {"type": "stripes", "period": 0.15}, "tags": ["test"]})
    assert not err and Path(data["path"]).exists()
    data, _ = call(server, "search_patterns", {"query": "striped"})
    assert data["results"][0]["id"] == "texture/striped-test"
    data, err = call(server, "get_pattern", {"pattern_id": "texture/striped-test"})
    assert data["pattern"]["params"]["period"] == 0.15
