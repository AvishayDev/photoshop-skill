---
title: Shadows (contact, cast, ambient occlusion)
category: lighting
tags: [shadow, cast shadow, contact shadow, ambient occlusion, grounding, penumbra]
aliases: [shadows]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Umbra,_penumbra_and_antumbra
    title: Umbra, penumbra and antumbra (Wikipedia)
    license: CC BY-SA 4.0
    supports: [penumbra grows with distance from the occluder]
related: [lighting/natural-light, techniques/seamless-compositing]
---
## Visual observations

- **Contact shadow / ambient occlusion:** darkest, tightest shadow exactly where objects touch the
  ground; present even under overcast light.
- **Cast shadow:** points away from the key light; length depends on light elevation; sharp near the
  contact point and progressively softer and lighter farther away (penumbra widens).
- Shadow colour is not black: outdoors it is tinted by the sky (blue) or the environment.

## Editing recipe

- `add_contact_shadow` first (opacity 0.6-0.85), then `add_cast_shadow` with the scene's light
  azimuth/elevation (softness 0.3 hard sun, 0.6-0.8 hazy), opacity 0.4-0.6.
- Tint shadow layers toward the ambient colour (color '#1a2233' for blue sky ambient).
- On uneven ground, mask the cast shadow where it would fall on raised objects, or warp it.
