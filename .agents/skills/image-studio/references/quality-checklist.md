# Inspection checklist

Look at the preview yourself first (`view_image`), at full size and as 100% crops of key areas
(`render_preview` with `region`). Then use the measurements.

**Request fidelity**: every requested element present? prohibited changes avoided? aspect/size right?
text spelled correctly?

**Anatomy & structure**: plausible proportions, limb count, joints, eyes; no melted or duplicated parts.

**Edges**: no halos or colour fringes (preview on '#ff00ff'), no hard sticker edges, hair/fur soft.

**Light**: single consistent key direction; shadows match it; subject brightness/colour fits surroundings
(`analyze_layer_integration`: warmth delta < 8, luminance delta < 0.12 unless intended).

**Grounding**: contact shadows present; feet/paws occluded by grass/water where appropriate.

**Reflections**: aligned with contact point, darker than the subject, distorted according to water state.

**Depth**: haze/contrast falloff with distance; focus and grain consistent per depth plane.

**Retouching**: no repeated clone patches (`inspect_image` flags them), no smudges.

**Tone**: no unintended clipping (`clipped_highlights` < 1-2%), no unintended colour cast.

**Composition**: clear focal point, horizon level, nothing important cut off at edges.

Prioritize by visual impact: wrong light/scale > edges/halos > colour mismatch > grain/sharpness > polish.
