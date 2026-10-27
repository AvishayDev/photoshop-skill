---
title: Layer masking
category: techniques
tags: [mask, layer mask, non-destructive, selection, feather, cut-out, edges]
aliases: [masks, masking]
confidence: high
reviewed: 2026-10-27
sources:
  - url: https://docs.gimp.org/3.0/en/gimp-layer-mask-add.html
    title: GIMP 3.0 manual - Add Layer Mask
    license: GFDL
    supports: [white reveals, black hides, masks keep pixels]
related: [techniques/seamless-compositing, techniques/background-removal, materials/fur]
---
## Visual observations

- Masks hide pixels without deleting them: white reveals, black hides, grey is partial. They can be
  re-edited at any time, which is why masking is preferred over erasing.

## Editing recipe

1. Separate the subject with `remove_background` (creates a mask) or `create_layer_mask` from a
   selection.
2. Inspect the edge with `render_preview` region at 100% (pass `region=[x, y, w, h]`), on a contrasting
   background (`background='#ff00ff'` reveals halos).
3. Refine: `edit_layer_mask` shrink 1 px to remove halos; blur 0.5-2 px for natural softness; contrast
   0.1-0.3 to firm up mushy edges; paint with value 0/1 to fix specific areas.
4. Gradient masks (`create_layer_mask` linear_gradient) blend layers smoothly, e.g. fading a sky
   replacement into the horizon.
5. Only `apply_mask` when a downstream tool requires baked alpha.

## Failure modes

- Halo (light or dark rim) from the original background; fix by shrinking + refeathering.
- Over-feathered, glowing edges on hard objects (products, architecture): keep 0.5-1 px there.

## Parameters

- Hard objects: feather 0.5-1 px. Hair/fur: 1-3 px plus painted irregularity. Atmospheric blends:
  linear gradients spanning 10-30% of the canvas.
