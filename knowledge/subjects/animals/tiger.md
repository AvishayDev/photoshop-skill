---
title: Tiger
category: subjects/animals
tags: [tiger, big cat, stripes, fur, predator, wildlife, felid]
aliases: [Panthera tigris, Bengal tiger, Amur tiger, Siberian tiger]
confidence: medium
reviewed: 2026-10-27
sources:
  - url: https://en.wikipedia.org/wiki/Tiger
    title: Tiger (Wikipedia), section Characteristics
    license: CC BY-SA 4.0
    supports: [proportions, stripes, face, coat colour, fur length]
  - url: https://commons.wikimedia.org/wiki/File:Panthera_tigris_altaica_13_-_Buffalo_Zoo.jpg
    title: Amur tiger photograph (Dave Pape)
    license: Public domain
    supports: [reference photo of head, coat and stripe layout]
related: [materials/fur, environments/forest, lighting/natural-light, techniques/seamless-compositing]
---
## Visual observations

- **Proportions:** long, muscular body; head-body ~1.4-2.8 m plus a tail about half the body length;
  shoulder height ~0.8-1.1 m. Legs look short relative to the heavy torso; forelimbs are noticeably
  thicker than hind limbs. Large, broad head.
- **Face:** rounded ears with a bold **white spot ringed in black on the back of each ear** (visible
  whenever the head is turned away); round pupils; pink triangular nose tip; white fur around the
  eyes, cheeks and muzzle with dark facial markings; long whiskers and a fur ruff framing the face
  (more pronounced in males and in Amur tigers).
- **Stripes:** black to dark brown, unique per individual. Mostly **vertical on the trunk**, horizontal
  on the limbs and forehead; denser toward the rear; trunk stripes can wrap under the belly. Tips are
  sharp/tapered and stripes frequently split or fork; left and right flanks are **not** mirror images.
  Tail has thick rings and a black tip.
- **Coat colour:** yellowish to reddish orange on top; white underside, inner legs and parts of the
  face. Northern (Amur) tigers are paler with longer, thicker winter fur; tropical tigers are shorter
  haired and more saturated orange.
- **Fur:** short (up to ~35 mm) on most tigers; belly hair is longer than back hair, so the belly
  silhouette is softer and fringed.
- **Paws:** large; four toes visible on the ground per foot (the front dewclaw is higher up).
  Claws are retracted when walking, so paw prints and ground contact show soft round pads.

## Editing recipe

1. Keep the tiger on its own layer with a mask; never erase fur edges destructively.
2. Match the coat's orange to the scene light: under warm sunrise light lift saturation slightly and
   push highlights warm; in shade or overcast light, desaturate and cool the white fur (it picks up
   blue sky or green canopy spill).
3. Edge: fur needs a *soft, irregular* mask edge (feather 1-2 px, then `edit_layer_mask` contrast
   ~0.2). Hard cut-outs read as stickers.
4. Ground it: `add_contact_shadow` under each paw (tight, dark) plus `add_cast_shadow` from the key
   light. Grass/leaves in front of the legs should occlude the paws (paint a mask or place foreground
   vegetation on a layer above).
5. Add `rim` light on the side facing a backlit sun; fur produces a bright halo when backlit.

## Failure modes

- Mirror-symmetric stripe patterns on both flanks, or stripes drawn horizontal on the body.
- Missing white ear spots on a head seen from behind.
- Uniform orange without the white underside / face pattern.
- Floating subject: no contact shadow, paws not occluded by grass, scale inconsistent with trees.
- Fur edge halo from a background-removed source photo (check with `analyze_layer_integration`).

## Parameters

- Fur edge: `feather_mask` 1-2 px at 1000-2000 px subject height; shrink mask 1 px if a halo appears.
- Contact shadow: blur 4-8 px, opacity 0.6-0.8; cast shadow softness 0.4-0.7 for sunrise light.

## Limitations

- Observations are from encyclopaedic description and reference photos; individual tigers vary.
- Realistic tiger *synthesis* needs a licensed photo asset or a local generative model; traditional
  compositing tools cannot paint convincing fur from scratch.
