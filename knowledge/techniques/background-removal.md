---
title: Background removal and replacement
category: techniques
tags: [background, remove background, cut-out, grabcut, sky replacement, mask, replace background]
aliases: [cut out, extract subject, background swap]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html
    title: OpenCV GrabCut tutorial
    license: Apache-2.0 (docs)
    supports: [rect initialization, seed refinement]
related: [techniques/layer-masking, techniques/seamless-compositing]
---
## Editing recipe

1. Duplicate the locked original; run `remove_background` on the copy:
   - plain studio backdrop -> method color_key (pick the backdrop colour, tolerance 30-60);
   - anything else -> grabcut with a tight `rect` around the subject; add foreground_points on missed
     subject parts and background_points on leftover background, then run again.
2. Inspect the mask on magenta (`render_preview` background '#ff00ff'); refine with `edit_layer_mask`.
3. New background on a layer *below* the subject; match horizon height and perspective first.
4. Re-light the subject to the new background (colour match, rim light, shadows); the old background's
   colour spill on edges must be neutralized (shrink mask 1 px, clipped hue/saturation on the edge).

## Failure modes

- Old background colour fringing; mismatched horizon; subject lit for a studio while the new scene is
  outdoors at sunset.

## Limitations

- GrabCut struggles with fine hair against busy backgrounds; the optional rembg method or manual mask
  painting helps.
