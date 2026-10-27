"""The mandatory planning protocol.

Before any image creation or editing, the agent must present a numbered plan
of at least 10 meaningful steps adapted to the request. The MCP server
refuses mutating tools until a plan has been accepted by :func:`validate_plan`
(see ``mcp_server.session``). ``draft_plan`` produces a request-specific
starting point that the agent should refine, not paste blindly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..core.ids import new_id
from ..errors import ValidationError

MIN_STEPS = 10
MIN_WORDS = 4
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "by", "at", "into", "from", "it",
         "its", "is", "be", "as", "that", "this", "then", "any", "all"}

# Each phase must be covered by at least one step (matched by keywords).
PHASES: dict[str, list[str]] = {
    "understand": ["define", "understand", "identify", "clarify", "requirement", "goal", "constraint", "inspect",
                   "analy", "review", "examine", "determine", "assess"],
    "act": ["create", "apply", "adjust", "build", "add", "mask", "crop", "remove", "generate", "composite",
            "transform", "edit", "paint", "clone", "heal", "blend", "place", "import", "grade", "retouch",
            "resize", "replace", "match", "correct", "rotate", "draw", "assemble", "extract", "separate",
            "construct", "render text", "type", "layer"],
    "verify": ["preview", "inspect", "verify", "check", "compare", "evaluate", "review", "quality"],
    "deliver": ["export", "save", "deliver", "report", "output"],
}


class PlanStep(BaseModel):
    number: int
    text: str


class Plan(BaseModel):
    id: str
    request: str
    steps: list[PlanStep]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    document_id: str | None = None
    status: str = "active"  # active | completed | abandoned
    notes: str | None = None

    def as_markdown(self) -> str:
        lines = [f"**Plan for:** {self.request}", ""]
        lines += [f"{s.number}. {s.text}" for s in self.steps]
        return "\n".join(lines)


def _norm(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOP}


def validate_plan(request: str, steps: list[str]) -> tuple[list[PlanStep], list[str]]:
    """Validate a proposed plan. Returns (steps, warnings); raises ValidationError when unacceptable."""
    if not request or len(request.strip()) < 3:
        raise ValidationError("The plan must restate the user's request")
    clean = [re.sub(r"^\s*(\d+[\.\)]|[-*])\s*", "", s).strip() for s in steps if s and s.strip()]
    problems: list[str] = []
    if len(clean) < MIN_STEPS:
        problems.append(f"The plan has {len(clean)} steps; at least {MIN_STEPS} meaningful steps are required.")
    short = [i + 1 for i, s in enumerate(clean) if len(s.split()) < MIN_WORDS]
    if short:
        problems.append(f"Steps {short} are too short to be meaningful (need >= {MIN_WORDS} words describing an "
                        "objective or operation).")
    seen: list[set[str]] = []
    dupes = []
    for i, s in enumerate(clean):
        toks = _norm(s)
        for j, prev in enumerate(seen):
            if toks and prev and len(toks & prev) / len(toks | prev) > 0.8:
                dupes.append((j + 1, i + 1))
        seen.append(toks)
    if dupes:
        problems.append(f"Steps are near-duplicates (padding is not allowed): {dupes}")
    text = " ".join(clean).lower()
    missing = [phase for phase, kws in PHASES.items() if not any(k in text for k in kws)]
    if missing:
        problems.append(f"The plan does not cover these phases: {missing} (understand the request, act, "
                        "inspect/verify the result, save/export and report).")
    if problems:
        raise ValidationError("Plan rejected: " + " ".join(problems),
                              hint="Write at least 10 distinct, request-specific steps; draft_plan can suggest a "
                                   "starting point.", details={"problems": problems})
    warnings = []
    req_tokens = _norm(request)
    if req_tokens and not (req_tokens & _norm(text)):
        warnings.append("The steps never mention the subject of the request; make sure the plan is adapted to it.")
    return [PlanStep(number=i + 1, text=s) for i, s in enumerate(clean)], warnings


def make_plan(request: str, steps: list[str], document_id: str | None = None) -> tuple[Plan, list[str]]:
    validated, warnings = validate_plan(request, steps)
    return Plan(id=new_id("plan"), request=request.strip(), steps=validated, document_id=document_id), warnings


# ----- drafting -----------------------------------------------------------------------------

def classify(request: str) -> str:
    r = request.lower()
    rules = [
        ("background_replacement", ["remove the background", "remove background", "replace the background",
                                    "background with", "cut out", "cutout", "isolate"]),
        ("object_removal", ["remove the", "erase", "get rid of", "clean up", "retouch", "blemish", "remove "]),
        ("crop_resize", ["crop", "resize", "aspect ratio", "straighten", "rotate", "upscale", "downscale"]),
        ("color_grade", ["color", "colour", "grade", "cinematic", "lighting", "brighter", "darker", "contrast",
                         "warm", "cool", "exposure", "mood", "vintage", "black and white"]),
        ("advertisement", ["advert", "ad ", "product", "poster", "banner", "flyer", "promo", "marketing", "text"]),
        ("realism", ["look like a realistic photo", "look like a photo", "rather than an illustration",
                     "more realistic", "less like an illustration"]),
        ("continue", ["continue", "existing project", "keep editing"]),
        ("scene_creation", ["create", "make", "generate", "paint", "design", "draw", "compose", "scene", "standing",
                            "photorealistic"]),
    ]
    for kind, kws in rules:
        if any(k in r for k in kws):
            return kind
    return "general_edit"


def _subjects(request: str) -> str:
    r = re.sub(r"^(please\s+)?(create|make|generate|draw|paint|edit|design)\s+(me\s+)?(a|an|the)?\s*", "",
               request.strip(), flags=re.I)
    return r.rstrip(".!") or request


def draft_plan(request: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a request-adapted plan draft (>= 10 steps) plus the detected request type."""
    kind = classify(request)
    s = _subjects(request)
    ctx = context or {}
    has_doc = bool(ctx.get("document_id"))
    common_head = [
        f"Define the intended result for '{s}': purpose, realism level, aspect ratio, output size and any explicit "
        "constraints or prohibited changes",
        "Inspect available capabilities (get_capabilities) and " + (
            "the existing project's layers, history and checkpoints" if has_doc else
            "decide on the canvas size and project name"),
    ]
    tail = [
        "Render a preview and inspect it visually and with inspect_image / analyze_layer_integration for seams, "
        "halos, lighting or scale mismatches and other defects",
        "Correct the most visible defects in order of impact, then render and inspect an updated preview",
        "Save the editable project (and a native .xcf/.ora copy), export the final image, and verify the exported "
        "file's format and dimensions",
        "Report the output paths, a summary of the work, remaining limitations and any required attribution",
    ]
    body: list[str]
    if kind == "scene_creation":
        body = [
            f"Search the knowledge base for existing notes on the subjects and environment in '{s}'",
            "Research reference images for the main subject's anatomy, proportions, silhouette and surface "
            "texture, recording sources and licenses",
            "Research the environment's structure, materials, depth layering and typical lighting, plus how the "
            "subject interacts with it (contact, occlusion, reflections, shadows)",
            "Write a visual specification: camera angle, composition and focal point, palette, key light "
            "direction and color temperature, depth of field",
            "Choose the creation method per element (procedural layers, licensed assets, local generative "
            "provider) and state limitations honestly if photorealism is not achievable",
            "Create a checkpoint, then build background, midground and atmosphere as separate named layers",
            "Add the main subject on its own layer with a clean mask, scaled and positioned for the chosen "
            "perspective",
            "Integrate the subject: match color and contrast, add contact and cast shadows, reflections or rim "
            "light consistent with the key light",
            "Apply global finishing on adjustment layers: color grade, atmospheric haze, depth blur and grain",
        ]
    elif kind == "background_replacement":
        body = [
            "Open the source image, keep the original layer locked and duplicate a working copy",
            "Analyze the subject's edges (hair, fur, transparency) and the original lighting direction and color",
            "Create a checkpoint, then separate the subject non-destructively with remove_background into a layer "
            "mask",
            "Refine the mask edges (feather, shrink to remove halos, paint fixes) and preview the cut-out on a "
            "contrasting background",
            f"Research or build the new background for '{s}' with matching perspective and horizon height, "
            "checking licenses of any assets",
            "Place the new background below the subject and match its scale, perspective and depth of field",
            "Match the subject to the new light: color match, exposure, rim light and contact shadows",
        ]
    elif kind == "object_removal":
        body = [
            "Open the image, keep the original locked and duplicate a working layer for retouching",
            "Identify the exact objects or blemishes to remove and the surrounding texture and structure lines",
            "Create a checkpoint before retouching",
            "Select each object precisely (selection or polygon) with a few pixels of margin",
            "Remove small objects with remove_object (inpainting) and inspect the result at 100% crop",
            "Rebuild structured areas (edges, horizons, patterns) with clone_stamp from matching source areas",
            "Blend repairs with heal_region so texture, color and light match the surroundings",
        ]
    elif kind == "crop_resize":
        body = [
            "Inspect the current document dimensions, resolution and the subject's position",
            "Determine the target aspect ratio or size and calculate the crop rectangle or scale factor",
            "Check composition of the proposed crop (rule of thirds, headroom, no cut-off limbs or text)",
            "Create a checkpoint so the original framing can be restored",
            "Apply the crop, rotation or resize with an appropriate interpolation method",
            "Check the new canvas boundaries for empty corners, aliasing or cut-off content",
            "Verify the resulting pixel dimensions against the requested size",
        ]
    elif kind == "color_grade":
        body = [
            "Open the image, keep the original locked and inspect its current tonal range and color balance",
            "Measure luminance, clipping and color cast with inspect_image to establish a baseline",
            f"Translate the requested look ('{s}') into concrete targets: contrast, highlight and shadow color, "
            "saturation, mood",
            "Create a checkpoint before grading",
            "Build the grade with non-destructive adjustment layers: exposure/levels, curves, color balance",
            "Add local adjustments with masks for the subject versus the background where needed",
            "Add finishing touches such as vignette, bloom or grain only if they support the look",
        ]
    elif kind == "advertisement":
        body = [
            "Inspect the supplied product images: resolution, lighting, angle and background",
            "Define the layout: format, hierarchy of product, headline and call to action, brand colors",
            "Create a checkpoint, then build the background with gradients or procedural textures",
            "Cut out each product non-destructively with masks and place them as separate layers",
            "Unify the products' lighting and color, and add grounded shadows and reflections",
            "Add editable text layers for headline and copy with legible size and contrast",
            "Align elements and check spacing, margins and visual balance",
        ]
    elif kind == "realism":
        body = [
            "Open the image and analyze which cues make it look illustrated (flat shading, clean edges, no "
            "noise, saturated colors)",
            "Research photographic references of the same subject for real lighting, texture and lens behavior",
            "Create a checkpoint, keep the original locked and duplicate a working layer",
            "Add realistic tonal response with curves and reduce over-saturated colors",
            "Introduce lens and sensor characteristics: subtle depth blur, chromatic aberration, vignette and grain",
            "Add or correct shadows, contact shadows and ambient occlusion where objects meet surfaces",
            "Compare against the references with compare_images and inspect_image",
        ]
    else:
        body = [
            "Open or create the document and protect the original pixels by locking and duplicating",
            f"Analyze what needs to change for '{s}' and which layers are affected",
            "Search the knowledge base and research references if real-world appearance matters",
            "Create a checkpoint before the main edits",
            "Apply the main edits on separate, named layers with masks rather than destructive erasing",
            "Use adjustment layers for color and tone so they remain editable",
            "Check edges, alignment and consistency of light across the edited regions",
        ]
    steps = common_head + body + tail
    return {"request_type": kind, "steps": steps, "step_count": len(steps),
            "note": "This is a draft. Adapt every step to the specific request and context before submitting it "
                    "with submit_plan, and show the final numbered plan to the user."}
