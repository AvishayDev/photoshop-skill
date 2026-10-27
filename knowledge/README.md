# Visual knowledge base

Version-controlled, reusable visual knowledge for image creation and editing. Agents **search this
first** (`search_knowledge`), reuse what is still relevant, research what is missing, and save
genuinely reusable lessons afterwards (`save_knowledge`). Git history is the memory: commit changes.

## Layout

| Folder | Contents |
| --- | --- |
| `subjects/` | Animals, birds, objects, people-agnostic subject appearance (anatomy, silhouette, markings) |
| `environments/` | Scenes: structure, depth layers, materials, typical light |
| `materials/` | Surface behaviour: fur, feathers, water, skin, metal... |
| `lighting/` | Light sources, shadows, reflections, atmosphere |
| `techniques/` | Editing procedures and tool recipes for this toolkit |

## Entry format

Markdown with YAML front matter (validated on every write and by `image-studio kb validate`):

```yaml
---
title: Tiger
category: subjects/animals
tags: [tiger, big cat, stripes]
aliases: [Panthera tigris]
confidence: medium        # low | medium | high (high requires sources)
reviewed: 2026-10-27
sources:
  - url: https://...
    title: ...
    license: CC BY-SA 4.0
    supports: [stripes, proportions]   # which observations the source backs
related: [materials/fur]
---
## Visual observations
## Editing recipe
## Failure modes
## Parameters
## Limitations
## Examples
```

## Rules

- Write observations in your own words. No copied articles, no embedded images, no hotlinked assets.
- Cite sources for factual claims; mark unsupported or uncertain points as such and keep confidence low.
- Record reference URLs and licenses, but do not store third-party images here.
- Prefer improving an existing entry over creating a near-duplicate.
- Only save what will help a *future* task; skip task-specific noise.
