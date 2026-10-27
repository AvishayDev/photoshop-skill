import pytest

from image_studio.errors import ValidationError
from image_studio.workflows.planning import classify, draft_plan, make_plan, validate_plan

GOOD = [
    "Define the goal: a photorealistic tiger in a dense forest at sunrise, 3:2, no text",
    "Inspect capabilities and search the knowledge base for tiger and forest notes",
    "Research tiger anatomy and stripe references with licenses recorded",
    "Research forest light at sunrise and how shafts of light pass through the canopy",
    "Write a visual specification for camera height, palette and key light direction",
    "Create a checkpoint and build the background forest layers with atmospheric depth",
    "Add the tiger on its own layer with a refined mask and correct scale",
    "Match the tiger's color and contrast to the forest light and add contact shadows",
    "Render a preview and inspect it for seams, halos and lighting errors",
    "Fix the detected defects and verify with a new preview",
    "Save the editable project, export the PNG and report paths and attribution",
]


def test_valid_plan():
    plan, warnings = make_plan("Create a photorealistic tiger in a forest", GOOD)
    assert len(plan.steps) == 11 and plan.steps[0].number == 1
    assert "1. Define the goal" in plan.as_markdown()


def test_too_few_steps():
    with pytest.raises(ValidationError, match="at least 10"):
        validate_plan("Crop the photo", GOOD[:9])


def test_padding_rejected():
    padded = GOOD[:8] + ["Check the image again carefully now"] * 3
    with pytest.raises(ValidationError, match="near-duplicates"):
        validate_plan("x request", padded)


def test_short_steps_rejected():
    with pytest.raises(ValidationError, match="too short"):
        validate_plan("Crop it", ["Crop."] * 10)


def test_missing_phase_rejected():
    steps = [f"Research reference number {i} about tiger stripes and fur" for i in range(12)]
    with pytest.raises(ValidationError):
        validate_plan("tiger", steps)


@pytest.mark.parametrize("request_text,kind", [
    ("Create a photorealistic tiger standing in a dense forest at sunrise.", "scene_creation"),
    ("Remove the background from this image and replace it with a snowy mountain.", "background_replacement"),
    ("Edit this photograph to make the lighting look cinematic.", "color_grade"),
    ("Create a professional product advertisement using these three images.", "advertisement"),
    ("Crop this photo to a square", "crop_resize"),
    ("Make this image look like a realistic photograph rather than an illustration.", "realism"),
    ("Remove the power lines from the sky", "object_removal"),
])
def test_drafts_are_valid_and_adapted(request_text, kind):
    d = draft_plan(request_text)
    assert d["request_type"] == kind
    assert d["step_count"] >= 10
    plan, _ = make_plan(request_text, d["steps"])
    assert len(plan.steps) >= 10


def test_classify_default():
    assert classify("do something") == "general_edit"
