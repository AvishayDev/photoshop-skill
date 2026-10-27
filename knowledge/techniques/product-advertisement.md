---
title: Product advertisement layout
category: techniques
tags: [advertisement, product, poster, banner, layout, typography, marketing, composite]
aliases: [ad, product shot, promo]
confidence: medium
reviewed: 2026-10-27
sources: []
related: [techniques/background-removal, techniques/seamless-compositing]
---
## Editing recipe

1. Choose the format first (e.g. 1080x1350 social, 1920x1080 banner) and a grid with 5-8% margins.
2. Background: gradient fill or soft procedural texture in brand colours; keep it low-contrast so the
   product pops.
3. Products: cut out non-destructively, unify their lighting direction and colour temperature, then
   ground them with contact shadows and optional floor reflections (`create_reflection` opacity
   0.15-0.3, ripple 0, fade 0.3 for glossy floors).
4. Hierarchy: one hero product largest; headline (bold, high contrast), sub-copy, call to action.
   Use `align_layers` for clean alignment.
5. Legibility check: text contrast against the background; preview at small size (max_size 400).

## Failure modes

- Products lit from different sides; text over busy areas; cramped margins.
