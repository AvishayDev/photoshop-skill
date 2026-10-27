---
title: Colour matching between layers
category: techniques
tags: [color, colour, match, grade, white balance, lab, integration, cast]
aliases: [color matching, colour transfer]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://doi.org/10.1109/38.946629
    title: Reinhard et al., Color Transfer between Images (IEEE CG&A 2001)
    license: Citation only
    supports: [mean/std transfer in a decorrelated colour space]
related: [techniques/seamless-compositing, lighting/natural-light]
---
## Visual observations

- A subject photographed under different light shows a colour cast and contrast unlike the plate.
  Matching means and spreads of colour statistics in a perceptual space (Lab) moves it most of the way.

## Editing recipe

1. `match_color` reference='below' (statistics of the area around the subject), strength 0.5-0.8.
   Full strength can make the subject look painted with the background colour.
2. Compare black and white points: sample the darkest shadows and brightest highlights in the plate
   near the subject; use clipped curves/levels on the subject to match them.
3. Re-check with `analyze_layer_integration` (warmth delta < 8, luminance delta < 0.12 unless intended).

## Failure modes

- Matching to a region that is not representative (e.g. sky behind a ground-level subject).
- Removing the subject's own colours (a tiger turning green in a forest).
