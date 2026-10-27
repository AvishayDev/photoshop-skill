---
title: Feathers and iridescence
category: materials
tags: [feathers, bird, iridescence, structural colour, plumage, sheen]
aliases: [plumage, structural color]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Structural_coloration
    title: Structural coloration (Wikipedia)
    license: CC BY-SA 4.0
    supports: [iridescence from microstructure, angle dependence]
  - url: https://en.wikipedia.org/wiki/Indian_peafowl
    title: Indian peafowl (Wikipedia)
    license: CC BY-SA 4.0
    supports: [peacock train colours are structural]
related: [subjects/birds/peacock]
---
## Visual observations

- Feathers overlap like roof tiles from head to tail; each has a central shaft and barbs, giving fine
  parallel texture.
- **Iridescent** plumage changes hue with viewing/light angle (green -> gold/bronze, blue -> violet)
  and goes dull brown/black in shade or when seen against the light.
- Pigmented feathers (browns, blacks) keep their colour under any angle; iridescent ones do not.
- Wet feathers clump, darken and lose iridescence.

## Editing recipe

- Simulate iridescence with two hue variants of the feather layer blended through a gradient mask
  aligned with the light direction (`adjust_colors` hue_saturation hue 15-35 on a duplicate).
- Add sparse specular highlights (small soft white points, screen, low opacity) on curved feather
  groups facing the light.

## Failure modes

- Constant hue across a curved iridescent surface; iridescent glow in deep shadow.
