---
title: Reflections on water
category: lighting
tags: [reflection, water, mirror, ripple, waves, fresnel, lake, ocean]
aliases: [water reflection, mirror reflection]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Fresnel_equations
    title: Fresnel equations (Wikipedia)
    license: CC BY-SA 4.0
    supports: [reflection strength depends on angle]
  - url: https://en.wikipedia.org/wiki/Specular_reflection
    title: Specular reflection (Wikipedia)
    license: CC BY-SA 4.0
    supports: [mirror geometry]
related: [materials/water, environments/ocean, subjects/birds/peacock]
---
## Visual observations

- A reflection is the scene seen from a point **mirrored below the water surface**, not just the image
  flipped: you see the underside of objects, and objects far behind the subject reflect lower.
  For subjects standing on the water plane, flipping about the contact line is a good approximation.
- Reflections are darker and lower in contrast than the object (water reflects only part of the light),
  and take on the water's tint.
- Calm water: sharp mirror. Ripples: the reflection is stretched vertically and broken into horizontal
  streaks. Choppy ocean: only a broken smear of colour; bright light sources form long vertical glitter
  paths.
- The reflection fades and blurs with distance from the contact point.

## Editing recipe

- `create_reflection` with axis_y = contact line. Calm lake: ripple_amplitude 0-1.5, blur 0.5-1,
  opacity 0.7-0.85. Ocean: ripple_amplitude 4-8, ripple_wavelength 10-20, blur 2-4, fade 0.4-0.6,
  opacity 0.4-0.6, tint = sampled water colour, tint_strength 0.3-0.5.
- Mask the reflection where foam or wave crests occlude it.

## Failure modes

- Perfect mirror reflection on choppy water; reflection brighter than the subject; reflection
  misaligned with the contact point (a gap between subject and reflection).
