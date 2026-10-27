---
title: Forest (temperate and tropical)
category: environments
tags: [forest, trees, canopy, vegetation, jungle, woodland, undergrowth, depth]
aliases: [woods, jungle, rainforest]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Aerial_perspective
    title: Aerial perspective (Wikipedia)
    license: CC BY-SA 4.0
    supports: [atmospheric depth]
  - url: https://en.wikipedia.org/wiki/Crepuscular_rays
    title: Crepuscular rays (Wikipedia)
    license: CC BY-SA 4.0
    supports: [light shafts]
related: [lighting/natural-light, subjects/animals/tiger, materials/fur]
---
## Visual observations

- **Vertical layering:** canopy, sub-canopy, shrub layer, ground cover (ferns, grasses, leaf litter),
  forest floor (soil, roots, fallen branches). Tropical forests are denser, greener and more humid;
  temperate forests show more trunk structure and leaf litter.
- **Depth:** trunks repeat at decreasing size and contrast with distance. Distant layers become lighter,
  lower in contrast and shifted toward the colour of the air (blue-green in clear air, warm gold at
  sunrise haze) - aerial perspective.
- **Light distribution:** mostly shade with scattered bright patches ("sun flecks") where light passes
  gaps; at low sun angles and with haze, visible shafts (crepuscular rays) radiate from the sun
  direction. Leaves glow yellow-green when backlit (translucency).
- **Colour:** shade areas are cool green/blue; sunlit patches warm; bark is grey-brown, never pure black.
- **Ground:** dappled shadows cast by foliage, darker under dense cover; subjects standing in the
  forest are partly occluded by grass and leaves.

## Editing recipe

1. Build in depth slices: far haze layer -> distant trees (lighter, lower contrast, slightly blurred)
   -> mid trees -> subject plane -> foreground leaves (darker, can be blurred for depth of field).
2. Use `create_procedural_layer` fog with vertical_falloff bottom at 0.2-0.4 opacity between slices.
3. Sun shafts: `add_lighting_effect` kind=god_rays from the sun position (x,y in 0..1), threshold
   0.6-0.75, then lower layer opacity to 0.4-0.7.
4. Dappled light on the subject: a soft clouds layer (`create_procedural_layer` clouds) clipped to the
   subject in multiply/overlay at low opacity breaks up uniform lighting.

## Failure modes

- Same tree repeated at the same scale (obvious cloning).
- Uniformly sharp background (no depth of field) behind a sharp subject.
- Subject lit by hard light while the surroundings are in diffuse shade.

## Parameters

- Distant layer: contrast -0.2..-0.4, gaussian blur 2-6 px at 2000 px width, fog colour sampled from sky.
- God rays: rays_length 0.3-0.5, intensity 0.5-0.8, blend screen.
