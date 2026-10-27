import pytest

from image_studio.backends.gimp import GimpBackend
from image_studio.backends.photoshop import PhotoshopBackend
from image_studio.core.capabilities import capability_report
from image_studio.errors import BackendUnavailableError, UnsupportedOperationError


def test_report_structure():
    rep = capability_report()
    assert rep["backends"]["pillow"]["available"] is True
    assert set(rep["backends"]) == {"pillow", "gimp", "photoshop"}
    assert rep["operations"]["filters"]["available"]
    assert any("generative" in s.lower() or "generative" in s for s in rep["limitations"])


def test_gimp_missing_is_reported(settings, monkeypatch):
    settings.gimp_executable = "/nonexistent/gimp"
    b = GimpBackend()
    st = b.status()
    assert not st.available and st.how_to_enable
    with pytest.raises(BackendUnavailableError):
        b.run_job([{"op": "probe"}])


def test_gimp_filter_requires_backend(editor, doc, settings):
    settings.gimp_executable = "/nonexistent/gimp"
    lid = editor.list_layers(doc)["layers"][0]["id"]
    with pytest.raises(UnsupportedOperationError):
        editor.apply_filter(doc, lid, "gegl:gaussian-blur", {"std-dev-x": 2.0})


def test_photoshop_optional_and_jsx_is_data_only(tmp_path):
    b = PhotoshopBackend()
    st = b.status()
    assert st.verified is False
    spec = {"width": 10, "height": 10, "layers": [{"name": 'evil"; app.quit(); "', "kind": "raster", "x": 0, "y": 0,
                                                   "png": "/tmp/a.png", "blend_mode": "multiply"}]}
    jsx = b.build_jsx(spec, tmp_path / "o.psd")
    assert 'evil\\"; app.quit(); \\"' in jsx  # JSON-escaped, not executable
    assert '"ps_blend": "MULTIPLY"' in jsx


def test_backend_selection_errors(editor):
    from image_studio.errors import ValidationError
    with pytest.raises(ValidationError):
        editor.backend_for("filter", "krita")
