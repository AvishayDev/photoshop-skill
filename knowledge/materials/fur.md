---
title: Fur
category: materials
tags: [fur, hair, animal, mammal, edge, rim light, translucency]
aliases: [pelt, coat]
confidence: medium
reviewed: 2026-10-27
sources: []
related: [subjects/animals/tiger, techniques/layer-masking, techniques/seamless-compositing]
---
## Visual observations

General practice from photography and compositing (not yet tied to fetched references):

- Fur edges are semi-transparent and irregular; individual hairs break the silhouette, especially
  against bright backgrounds.
- Fur direction follows the body: flows from head to tail, outward from the spine, and changes
  direction at joints; lighting reveals direction as streaky highlights.
- Backlit fur glows (rim light) because thin hairs scatter light; front-lit fur looks flatter.
- Shadowed fur picks up the environment's colour (green canopy, blue sky).
- Long fur clumps; short fur reads as a velvety texture with fine noise.

## Editing recipe

- Mask: feather 1-2 px, then `edit_layer_mask` contrast 0.1-0.3; paint the mask with a small soft brush
  at low value along the edge to create hair-like irregularity rather than a smooth curve.
- Use `select_by_color` on a plain backdrop with tolerance 30-50 and feather to retain fine hairs.
- Match grain: subject cut-outs are often cleaner than the plate; `add_noise` 0.01-0.03 on the subject.

## Failure modes

- Hard, smooth outline ("sticker" look); colour fringe/halo from the original background.
- Fur sharper than the surrounding plane in focus.
