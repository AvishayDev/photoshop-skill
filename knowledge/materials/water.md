---
title: Water (surface, transparency, wetness)
category: materials
tags: [water, liquid, transparency, refraction, wet, ripple, foam, reflection]
aliases: [liquid surface, wet surface]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Fresnel_equations
    title: Fresnel equations (Wikipedia)
    license: CC BY-SA 4.0
    supports: [reflection grows at grazing angles]
  - url: https://en.wikipedia.org/wiki/Snell%27s_law
    title: Snell's law (Wikipedia)
    license: CC BY-SA 4.0
    supports: [refraction bends submerged parts]
related: [lighting/water-reflections, environments/ocean]
---
## Visual observations

- **Fresnel:** water reflects little when viewed straight down and a lot at grazing angles; distant
  water is mostly reflection, near water shows depth and transparency.
- **Refraction:** submerged parts of objects appear displaced and shortened at the waterline; the
  boundary is broken by ripples.
- **Contact:** objects standing in water produce rings/ripples and a thin bright meniscus line where
  they enter the surface; wet surfaces darken and gain specular highlights.
- **Depth colour:** shallow water over sand is turquoise; deeper water shifts to blue/teal; turbid water
  is green-brown and opaque.

## Editing recipe

- Waterline on a subject: mask the part below the waterline down to ~20-40% visibility, offset it a few
  px sideways (refraction), tint it with the water colour, and add a thin light line at the waterline.
- Ripple rings: ellipse shape layers (stroke only, light colour, low opacity), squashed vertically
  to match the viewing angle, blurred 1-2 px, screen/soft_light.
- Wet darkening: clipped `exposure` adjustment ev -0.3..-0.7 on the wet part, plus small highlights.
