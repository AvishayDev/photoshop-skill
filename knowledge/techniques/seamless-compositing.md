---
title: Seamless compositing
category: techniques
tags: [composite, compositing, integration, photomontage, lighting match, perspective, scale]
aliases: [photo compositing, montage]
confidence: medium
reviewed: 2026-10-27
sources: []
related: [techniques/color-matching, techniques/layer-masking, lighting/natural-light]
---
## Visual observations

General compositing practice (checklist; each item is verifiable on the preview):

1. **Perspective & horizon:** the subject's camera height and lens must match the plate; the horizon
   passes through the same height on all elements standing on the ground plane.
2. **Scale:** compare with known-size objects (doors, trees, grass blades).
3. **Light direction, hardness, colour:** identical across elements.
4. **Shadows:** contact shadow + cast shadow consistent with the key light.
5. **Colour & contrast:** subject black/white points and saturation similar to nearby plate areas.
6. **Atmosphere:** distant subjects need haze; foreground subjects need none.
7. **Focus & grain:** same depth of field, sharpness and noise as the plate at that depth.
8. **Interaction:** occlusion by foreground elements, environmental colour spill, reflections.

## Editing recipe

1. Place the subject on its own layer (mask, not erase) and position/scale it (`transform_layer`).
2. `match_color` (clipped adjustment layer, strength 0.5-0.8) then fine-tune with clipped curves.
3. `add_contact_shadow` and `add_cast_shadow` using the scene's key light.
4. Add rim/spill light with `add_lighting_effect` (rim, clipped) using the environment colour.
5. Match focus/grain: `blur_layer` on subject or background; `apply_filter add_noise` to match.
6. Run `analyze_layer_integration` and fix the listed findings; check the preview at 100%.
7. Global grade on top with adjustment layers to unify everything.

## Failure modes

- Every element individually fine but lit from different directions.
- Subject "floats" (no contact shadow, no occlusion).
- Subject sharper/cleaner than the plate.
