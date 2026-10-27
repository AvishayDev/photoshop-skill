---
title: Cinematic colour grading
category: techniques
tags: [cinematic, grade, color grading, teal orange, film look, mood, contrast, lighting]
aliases: [film look, movie look]
confidence: medium
reviewed: 2026-10-27
sources: []
related: [lighting/natural-light, techniques/color-matching]
---
## Editing recipe (all as adjustment layers)

1. Normalize: `levels`/`exposure` so highlights are not clipped (inspect_image clipped_highlights < 1%).
2. Contrast: gentle S-curve `curves` points [[0,12],[64,52],[192,206],[255,245]] (lifted blacks,
   rolled-off highlights read as filmic).
3. Split tone: `color_balance` shadows [-0.15, 0, 0.2] (teal), highlights [0.2, 0, -0.15] (warm);
   keep skin/subject natural with a mask.
4. Reduce overall saturation slightly (`hue_saturation` saturation -0.1) and boost `vibrance` +0.1.
5. Shape light: darken edges with `vignette` (amount 0.25-0.4) or a radial-gradient-masked exposure.
6. Finish: subtle `bloom` on highlights and `add_noise` grain 0.01-0.02 (monochrome).

## Failure modes

- Orange/teal pushed so far that skin and neutrals look radioactive; crushed blacks with no detail.
