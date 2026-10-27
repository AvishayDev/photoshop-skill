"""End-to-end example: "Create a peacock standing in the ocean, with realistic water reflections."

Drives the image-studio MCP server over stdio with the official MCP client - the same protocol Claude
Code and Codex use - and follows the skill's workflow: capabilities -> knowledge -> 10+ step plan ->
research -> licensed assets -> layered compositing -> inspection -> export -> knowledge update.

Assets (fetched live, licenses recorded in the project and the export's .credits.json):
  * Plate: "View calm ocean horizon sandy" - CC0 1.0 (via Openverse)
  * Subject: "Peacock standing on grassy field - India.jpg" by Ksheera Piraati - CC BY 4.0 (Wikimedia Commons)

Run:  python examples/peacock_in_the_ocean.py   (needs network access; ~1-2 minutes)
Output: projects/peacock-in-the-ocean/exports/
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PLATE_KEY = "openverse:58b9e852-e5d3-4a89-9e7e-6006288d3f3f"
PEACOCK_KEY = "wikimedia_commons:193577964"
STUDY_KEYS = [PEACOCK_KEY, "wikimedia_commons:90814713"]

W, H = 1600, 900
HORIZON_Y = 405          # camera roughly at a standing peacock's head height
FEET = (700, 800)        # where the bird stands in the shallow water


def out(res):
    data = getattr(res, "structured_content", None) or getattr(res, "structuredContent", None)
    if data is None:
        data = json.loads(res.content[0].text)
    if isinstance(data, dict) and data.get("ok") is False:
        raise RuntimeError(json.dumps(data, indent=1))
    return data


async def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = {**os.environ, "IMAGE_STUDIO_WORKSPACE": str(repo / "projects")}
    params = StdioServerParameters(command=sys.executable, args=["-m", "image_studio.cli", "serve"], env=env)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        call = s.call_tool

        caps = out(await call("get_capabilities", {}))
        print("backends:", {k: v["available"] for k, v in caps["backends"].items()})
        for q in ("peacock feathers", "ocean water reflections", "shadows natural light sunset"):
            hits = out(await call("search_knowledge", {"query": q}))["results"]
            print(f"knowledge '{q}':", [h["path"] for h in hits[:3]])

        request = "Create a peacock standing in the ocean, with realistic water reflections."
        steps = [
            "Define the result: photorealistic 16:9 image, a male peacock standing in shallow ocean water at "
            "sunset, its reflection on the wet surface as the secondary focal element",
            "Check capabilities and read the knowledge entries for peacock, feathers, ocean, water "
            "reflections and natural light",
            "Research peacock references for side-view silhouette, train length and leg structure, recording "
            "licenses",
            "Research and choose a public-domain ocean plate whose light (low sun, wet reflective sand) "
            "supports a believable reflection",
            "Analyze the plate's light: sun position low on the left, backlight, warm highlights and cool "
            "shadows, and record observations",
            "Write the visual spec: horizon at the bird's head height, bird facing the sun, rim light on edges "
            "facing the sun, long faint shadow toward the camera, mirror-like reflection broken by small "
            "ripples",
            "Create the project and a checkpoint, then place and scale the ocean plate so the horizon sits "
            "at the planned height",
            "Retouch the plate: remove distracting people with inpainting so nothing contradicts the bird's "
            "scale",
            "Import the peacock photo as a smart layer and separate it from the grass with a GrabCut mask, "
            "then refine the mask edge",
            "Integrate the subject: neutralize green grass spill, match colour to the sunset and darken it "
            "for backlight with clipped adjustment layers",
            "Add a warm rim light from the sun side clipped to the bird",
            "Submerge the feet: hide the lower legs behind the waterline and add subtle ripple rings",
            "Create the water reflection mirrored at the waterline with Fresnel darkening, tint and ripples",
            "Add a faint long cast shadow and a contact shadow consistent with the low sun",
            "Apply a unifying grade, vignette and film grain on adjustment layers",
            "Render a preview, inspect it visually and with analyze_layer_integration, and list defects",
            "Correct the most visible defects and re-render to verify the fixes",
            "Save the layered project as OpenRaster (and XCF when GIMP is available) and export PNG and JPEG "
            "with verification",
            "Report output paths, limitations and the required CC BY attribution, and save reusable "
            "knowledge",
        ]
        plan = out(await call("submit_plan", {"request": request, "steps": steps}))
        print(plan["plan_markdown"])

        d = out(await call("create_project", {"name": "Peacock in the Ocean", "width": W, "height": H,
                                              "background": None}))["document_id"]
        print("document:", d)

        # ---- research ---------------------------------------------------------------------------
        refs = []
        for key in STUDY_KEYS + [PLATE_KEY]:
            f = out(await call("fetch_reference", {"document_id": d, "reference_key": key}))
            refs.append(f["reference_id"])
            print("reference:", f["title"], "|", f["license"]["short_name"])
        ana = out(await call("analyze_visual_references", {"document_id": d, "reference_ids": refs}))
        print("contact sheet:", ana["contact_sheet"])
        for aspect, text, ids in [
            ("silhouette", "Walking male seen from the side: small head and body, long closed train trailing "
             "on the ground about 2.5-3x the body length, slender pale legs.", [refs[0]]),
            ("train presence", "A male without a long train (moulted or immature - not determinable from this "
             "photo) shows chestnut primaries and a short brown tail; a full train is not always present.",
             [refs[1]]),
            ("plate light", "Sun low on the left just above the horizon; wet sand mirrors the sky; strong "
             "backlight means subjects facing the camera are mostly in shadow with bright rims.", [refs[2]]),
        ]:
            out(await call("record_observation", {"document_id": d, "aspect": aspect, "observation": text,
                                                  "reference_ids": ids, "confidence": "medium"}))

        # ---- plate ---------------------------------------------------------------------------------
        plate_ref = out(await call("fetch_reference", {"document_id": d, "reference_key": PLATE_KEY,
                                                       "size": "full", "purpose": "composite"}))
        pw, ph = plate_ref["size"]
        span = (H - HORIZON_Y) / (0.79 - 0.593)       # plate rows 0.593 (horizon) .. 0.79 fill the bottom
        scale = span / ph
        plate = out(await call("import_image_as_layer", {
            "document_id": d, "reference_id": plate_ref["reference_id"], "name": "Ocean plate",
            "x": 0, "y": int(HORIZON_Y - 0.593 * span), "scale": scale}))["layer_id"]
        out(await call("create_checkpoint", {"document_id": d, "name": "plate placed"}))
        retouch = out(await call("duplicate_layer", {"document_id": d, "layer_id": plate,
                                                     "name": "Plate retouch"}))["layer_id"]
        out(await call("set_layer_visibility", {"document_id": d, "layer_id": plate, "visible": False}))
        out(await call("rasterize_layer", {"document_id": d, "layer_id": retouch}))
        out(await call("remove_object", {"document_id": d, "layer_id": retouch, "region": "rect",
                                         "rect": [1270, 845, 40, 55], "dilate": 6}))

        # ---- subject ---------------------------------------------------------------------------------
        bird_ref = out(await call("fetch_reference", {"document_id": d, "reference_key": PEACOCK_KEY,
                                                      "size": "large", "purpose": "composite"}))
        bw, bh = bird_ref["size"]
        s_bird = 920 / (0.47 * bw)                     # bird + train spans ~47% of the photo width
        dw, dh = bw * s_bird, bh * s_bird
        bird = out(await call("import_image_as_layer", {
            "document_id": d, "reference_id": bird_ref["reference_id"], "name": "Peacock",
            "scale": s_bird, "x": int(FEET[0] - 0.45 * dw), "y": int(FEET[1] - 0.61 * dh)}))["layer_id"]
        info = out(await call("get_layer_info", {"document_id": d, "layer_id": bird}))["layer"]
        bx, by = info["bounds"]["x"], info["bounds"]["y"]
        bwid, bhei = info["bounds"]["width"], info["bounds"]["height"]
        rect = [bx + 0.355 * bwid, by + 0.345 * bhei, 0.49 * bwid, 0.31 * bhei]
        res = out(await call("remove_background", {"document_id": d, "layer_id": bird, "rect": rect,
                                                   "edge_feather": 1.0}))
        print("subject fraction:", res["subject_fraction"])
        out(await call("edit_layer_mask", {"document_id": d, "layer_id": bird, "operation": "shrink", "amount": 1}))
        out(await call("feather_mask", {"document_id": d, "layer_id": bird, "radius": 1.2}))

        # ---- integration (pass 1) ----------------------------------------------------------------------
        out(await call("adjust_colors", {"document_id": d, "layer_id": bird, "adjustment": "hue_saturation",
                                         "params": {"saturation": -0.25}, "as_adjustment_layer": True,
                                         "name": "Peacock · tame grass spill"}))
        match = out(await call("match_color", {"document_id": d, "layer_id": bird, "strength": 0.45}))["layer_id"]
        backlight = out(await call("adjust_colors", {
            "document_id": d, "layer_id": bird, "adjustment": "exposure", "params": {"ev": -0.9},
            "as_adjustment_layer": True, "name": "Peacock · backlight"}))["layer_id"]
        warmth = out(await call("adjust_colors", {
            "document_id": d, "layer_id": bird, "adjustment": "temperature_tint",
            "params": {"temperature": 0.35, "tint": 0.05}, "as_adjustment_layer": True,
            "name": "Peacock · sunset warmth"}))["layer_id"]
        rim = out(await call("add_lighting_effect", {"document_id": d, "kind": "rim", "layer_id": bird,
                                                     "light_azimuth": 200, "width": 3, "intensity": 0.9,
                                                     "color": "#ffc27a"}))["layer_id"]
        # waterline: hide the feet below the surface and add ripples
        out(await call("edit_layer_mask", {"document_id": d, "layer_id": bird, "operation": "gradient",
                                           "start": [0, FEET[1] - 18], "end": [0, FEET[1] + 4],
                                           "combine": "multiply"}))
        for i, (rw, rh_, op) in enumerate([(70, 10, 0.55), (120, 16, 0.35)]):
            rid = out(await call("create_shape_layer", {"document_id": d, "shape": "ellipse",
                                                        "x": FEET[0] - rw / 2 + 4, "y": FEET[1] - 14 - rh_ / 2,
                                                        "width": rw, "height": rh_, "fill": None,
                                                        "stroke": "#ffe2bf", "stroke_width": 1.5,
                                                        "name": f"Ripple {i + 1}"}))["layer_id"]
            out(await call("set_layer_properties", {"document_id": d, "layer_id": rid, "opacity": op,
                                                    "blend_mode": "screen"}))
            out(await call("blur_layer", {"document_id": d, "layer_id": rid, "radius": 1.5}))
        reflection_args = {"document_id": d, "layer_id": bird, "axis_y": FEET[1] - 12, "opacity": 0.5,
                           "fade": 0.55, "blur": 2.0, "ripple_amplitude": 2.5, "ripple_wavelength": 14,
                           "tint": "#c98a5a", "tint_strength": 0.35, "darken": 0.25}
        shadow_args = {"document_id": d, "layer_id": bird, "light_azimuth": 200, "light_elevation": 9,
                       "ground_y": FEET[1] - 12, "softness": 0.7, "opacity": 0.22, "color": "#2a1a12"}
        refl = out(await call("create_reflection", reflection_args))["layer_id"]
        shadow = out(await call("add_cast_shadow", shadow_args))["layer_id"]

        # ---- global finishing ------------------------------------------------------------------------
        curves = out(await call("adjust_curves", {"document_id": d, "layer_id": None,
                                                  "points": [[0, 10], [64, 58], [192, 204], [255, 250]]}))
        glow = out(await call("add_lighting_effect", {"document_id": d, "kind": "point", "x": 0.2, "y": 0.18,
                                                      "radius": 0.9, "intensity": 0.35, "color": "#ffcf8a"}))
        top = out(await call("create_layer", {"document_id": d, "name": "Vignette + grain", "fill_color": "#808080"}))
        out(await call("apply_filter", {"document_id": d, "layer_id": top["layer_id"], "filter": "add_noise",
                                        "params": {"amount": 0.05, "seed": 7}}))
        out(await call("apply_filter", {"document_id": d, "layer_id": top["layer_id"], "filter": "vignette",
                                        "params": {"amount": 0.55, "radius": 0.6, "softness": 0.9}}))
        out(await call("set_layer_properties", {"document_id": d, "layer_id": top["layer_id"],
                                                "blend_mode": "overlay", "opacity": 0.5}))
        first = out(await call("render_preview", {"document_id": d, "max_size": 1600}))
        print("pass-1 preview:", first["preview_path"])
        print("pass-1 integration:", [f["issue"] for f in out(await call(
            "analyze_layer_integration", {"document_id": d, "layer_id": bird}))["findings"]])

        # ---- correction round ---------------------------------------------------------------------------
        # Defects seen when LOOKING at the pass-1 preview (and its magenta-background cut-out check):
        #  1. GrabCut kept grass under and around the train (green train vs. green grass is ambiguous)
        #  2. the rim light reads as a bright sticker outline
        #  3. the bird is cooler/more saturated than the sunset and sharper than the soft plate
        #  4. the train ends in a hard straight cut; a person remnant is still visible; glow washes out the sky
        def P(u, v):  # normalized photo coordinates -> document coordinates
            return [bx + u * bwid, by + v * bhei]

        fg = [P(u / 960, v / 640) for u, v in [(360, 245), (372, 280), (430, 295), (470, 300), (540, 315),
                                               (620, 345), (700, 375), (760, 392), (432, 360)]]
        bg = [P(u / 960, v / 640) for u, v in [(470, 372), (520, 362), (560, 372), (600, 382), (640, 392),
                                               (680, 402), (720, 412), (760, 418), (800, 404), (500, 345),
                                               (400, 400), (455, 410), (560, 300), (640, 320), (720, 350),
                                               (380, 330), (340, 300)]]
        out(await call("remove_background", {"document_id": d, "layer_id": bird, "rect": [
            bx + 340 / 960 * bwid, by + 225 / 640 * bhei, 470 / 960 * bwid, 200 / 640 * bhei],
            "foreground_points": fg, "background_points": bg, "edge_feather": 1.0}))
        out(await call("edit_layer_mask", {"document_id": d, "layer_id": bird, "operation": "shrink", "amount": 1}))
        for poly in ([(0.5416, 0.5203), (0.5825, 0.5341), (0.6285, 0.5533), (0.6745, 0.5663), (0.7205, 0.5816),
                      (0.7716, 0.5954), (0.8074, 0.6015), (0.8304, 0.6069), (0.838, 0.6644), (0.5365, 0.6644),
                      (0.5289, 0.5724)],
                     [(0.626, 0.4805), (0.8431, 0.4805), (0.8431, 0.5923), (0.8074, 0.5877), (0.7563, 0.5755),
                      (0.7052, 0.5625), (0.6643, 0.551), (0.6336, 0.5433)]):
            out(await call("create_selection", {"document_id": d, "shape": "polygon",
                                                "points": [P(u, v) for u, v in poly], "feather": 2}))
            out(await call("edit_layer_mask", {"document_id": d, "layer_id": bird, "operation": "fill_selection",
                                               "value": 0.0}))
        out(await call("modify_selection", {"document_id": d, "operation": "clear"}))
        cut = out(await call("render_preview", {"document_id": d, "layer_id": bird, "background": "#ff00ff"}))
        print("cut-out check:", cut["preview_path"])
        # re-apply the waterline and fade the train's tail into the water
        out(await call("edit_layer_mask", {"document_id": d, "layer_id": bird, "operation": "gradient",
                                           "start": [0, FEET[1] - 18], "end": [0, FEET[1] + 4],
                                           "combine": "multiply"}))
        out(await call("edit_layer_mask", {"document_id": d, "layer_id": bird, "operation": "gradient",
                                           "start": P(0.6796, 0)[:1] + [0], "end": P(0.8252, 0)[:1] + [0],
                                           "combine": "multiply"}))
        for lid, params in ((match, {"strength": 0.7}), (backlight, {"ev": -1.1}),
                            (warmth, {"temperature": 0.45, "tint": 0.08}),
                            (curves["layer_id"], {"points": [[0, 0], [64, 56], [192, 204], [255, 252]]})):
            out(await call("update_adjustment_layer", {"document_id": d, "layer_id": lid, "params": params}))
        out(await call("adjust_colors", {"document_id": d, "layer_id": bird, "adjustment": "hue_saturation",
                                         "params": {"saturation": -0.12}, "as_adjustment_layer": True,
                                         "name": "Peacock · less saturation"}))
        out(await call("set_layer_opacity", {"document_id": d, "layer_id": glow["layer_id"], "opacity": 0.45}))
        out(await call("blur_layer", {"document_id": d, "layer_id": bird, "radius": 1.4}))
        for lid in (rim, refl, shadow):
            out(await call("delete_layer", {"document_id": d, "layer_id": lid}))
        out(await call("add_lighting_effect", {"document_id": d, "kind": "rim", "layer_id": bird,
                                               "light_azimuth": 200, "width": 2, "intensity": 0.45,
                                               "color": "#ffc27a"}))
        out(await call("create_reflection", reflection_args))
        shadow = out(await call("add_cast_shadow", {**shadow_args, "opacity": 0.15}))["layer_id"]
        out(await call("blur_layer", {"document_id": d, "layer_id": shadow, "radius": 5}))
        out(await call("remove_object", {"document_id": d, "layer_id": retouch, "region": "rect",
                                         "rect": [1262, 815, 56, 90], "dilate": 6}))
        out(await call("clone_stamp", {"document_id": d, "layer_id": retouch, "source_point": [1225, 885],
                                       "strokes": [[[1280, 885], [1300, 885]], [[1280, 898], [1302, 898]],
                                                   [[1285, 872], [1298, 872]]],
                                       "brush_size": 30, "hardness": 0.4}))

        # ---- inspect --------------------------------------------------------------------------------
        prev = out(await call("render_preview", {"document_id": d, "max_size": 1600}))
        print("preview:", prev["preview_path"])
        integ = out(await call("analyze_layer_integration", {"document_id": d, "layer_id": bird}))
        print("integration findings:", json.dumps(integ["findings"], indent=1))
        insp = out(await call("inspect_image", {"document_id": d}))
        print("defects:", insp["defects"])

        # ---- deliver ------------------------------------------------------------------------------------
        saved = out(await call("save_document", {"document_id": d, "format": "ora"}))
        print("layered project:", saved["native_file"])
        if caps["backends"]["gimp"]["available"]:
            print("xcf:", out(await call("save_document", {"document_id": d, "format": "xcf"}))["native_file"])
        png = out(await call("export_png", {"document_id": d}))
        jpg = out(await call("export_jpeg", {"document_id": d, "quality": 90}))
        print("exports:", png["export_path"], jpg["export_path"], png["verification"])
        print("credits:", png["credits"])
        manifest = out(await call("get_project_manifest", {"document_id": d}))
        print("project folder:", manifest["project_path"])
        out(await call("save_knowledge", {
            "path": "subjects/birds/peacock", "sections": {
                "Visual observations": "- Not every male carries a full train: a male photographed without one "
                                       "(moulted after breeding or immature - the photo alone cannot tell) shows "
                                       "chestnut primaries and a short brown tail. Check which state the request "
                                       "implies.",
                "Failure modes": "- GrabCut confuses the green train with green grass/foliage; add background "
                                 "seed points along the train's lower edge and paint/polygon-mask leftovers, "
                                 "then check the cut-out on magenta."},
            "sources": [{"url": "https://commons.wikimedia.org/wiki/File:Peacock_standing_locking_stunning.jpg",
                         "title": "Male peacock without train", "license": "CC BY-SA 4.0",
                         "supports": ["male without train"]}]}))
        out(await call("complete_plan", {"summary": "Peacock composited into a CC0 sunset ocean plate.",
                                         "unresolved_issues": [
                                             "The plate is upscaled ~1.3x, so fine detail is soft; the bird was "
                                             "softened to match.",
                                             "The train's tail end retains some grass texture under the "
                                             "water-fade."]}))


if __name__ == "__main__":
    anyio.run(main)
