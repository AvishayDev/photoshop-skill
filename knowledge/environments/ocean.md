---
title: Ocean and sea surface
category: environments
tags: [ocean, sea, water, waves, horizon, beach, coast, seascape]
aliases: [seascape, sea, shoreline]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Fresnel_equations
    title: Fresnel equations (Wikipedia)
    license: CC BY-SA 4.0
    supports: [reflectivity vs viewing angle]
  - url: https://en.wikipedia.org/wiki/Aerial_perspective
    title: Aerial perspective (Wikipedia)
    license: CC BY-SA 4.0
    supports: [horizon haze]
related: [materials/water, lighting/water-reflections, subjects/birds/peacock]
---
## Visual observations

- **Horizon:** perfectly level; place at roughly one third from top or bottom, never through the
  subject's neck. Its height equals the camera's eye level - subjects of similar size standing on the
  same plane have their eyes near the horizon when the camera is at their eye height.
- **Colour gradient:** water near the horizon reflects the sky at grazing angles and is bright and
  low-contrast; water near the camera shows more of its own colour (deep blue/teal) and texture.
- **Waves:** shrink and compress vertically toward the horizon (perspective); wave texture is
  anisotropic - wider than tall. Shallow water near the shore is turquoise over sand, foam lines run
  parallel to the shore.
- **Haze:** distant water and sky merge in a hazy band near the horizon.
- **Specular glints:** sun reflection forms a vertical glitter path toward the viewer below the sun.

## Editing recipe

1. Sky gradient (`create_procedural_layer` sky) + water base (`create_procedural_layer` water) split at
   the horizon line; add a thin haze band (fog layer masked to a horizontal strip).
2. Compress wave texture toward the horizon (`transform_layer` perspective on the water layer: narrow
   the top edge less, squash vertically).
3. Sun path: a narrow vertical radial/point light below the sun position on the water, blend screen.
4. Subjects in the water: waterline mask, ripples, darker wet zone, broken reflection.

## Failure modes

- Tilted horizon; reflections longer/shorter than physically plausible.
- Uniform wave scale across the whole surface (no perspective).
- Saturated blue right up to the horizon (missing Fresnel brightening and haze).
