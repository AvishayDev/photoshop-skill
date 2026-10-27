---
title: Clone stamp and healing
category: techniques
tags: [clone, clone stamp, heal, healing brush, retouch, repair, remove object, texture]
aliases: [rubber stamp, healing brush, spot healing]
confidence: high
reviewed: 2026-10-27
sources:
  - url: https://docs.gimp.org/3.0/en/gimp-tool-clone.html
    title: GIMP 3.0 manual - Clone tool
    license: GFDL
    supports: [source offset, aligned mode]
  - url: https://docs.gimp.org/3.0/en/gimp-tool-heal.html
    title: GIMP 3.0 manual - Heal tool
    license: GFDL
    supports: [heal blends texture with surrounding colour]
related: [techniques/seamless-compositing]
---
## Visual observations

- Clone copies pixels from a source offset; heal copies texture but adapts colour/brightness to the
  destination surroundings. Neither invents new objects: they extend or repair existing texture.

## Editing recipe

1. Always retouch on a duplicate of the original (the original stays locked).
2. Small blemishes on uniform areas: `heal_region` without source_point (spot healing).
3. Structured areas (horizons, edges, patterns): `clone_stamp` with source_point on the same line of
   structure, aligned=true, strokes following the structure.
4. Organic texture (grass, sand, foliage): several short strokes from *different* sources, opacity
   0.6-0.9, hardness 0.3-0.6, then `heal_region` over seams.
5. Large objects: `remove_object` first (inpainting), then clone structure back in, then heal.
6. Check with `inspect_image` - it flags repeated identical patches (tell-tale cloning).

## Failure modes

- Repeated identical patterns; hard dab edges; cloning across a lighting gradient (wrong brightness;
  use heal instead); smudgy inpainting on big areas.

## Parameters

- brush_size ~1.5-3x the blemish width; spacing default; hardness 0.5 general, 0.8+ for hard edges.
- Native GIMP tools: `backend='gimp'` uses gimp-clone / gimp-heal with GIMP's "2. Hardness" brushes.
